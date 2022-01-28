# this basic issuer displays a QR code with the path to the endpoint used by wallet
# 


from flask import Flask, jsonify, request, Response, render_template_string
from flask_qrcode import QRcode
import json
from datetime import timedelta, datetime
import uuid
import didkit
import redis


app = Flask(__name__)
qrcode = QRcode(app)

# Redis init red = redis.StrictRedis()
# Redis is used to store session data
red= redis.Redis(host='localhost', port=6379, db=0)

# one private key for ethereum -JWK format 
issuer_key = json.dumps({"alg":"ES256K-R",
                        "crv":"secp256k1",
                        "d":"7Y_O4Vl4nr_znkq9S-Kb2sh8B-9jYST8kZTYdr9KUhU",
                        "kty":"EC",
                        "x":"Ocenh6RngwFPSNX9YZgif9Kg3stxedjLUq5Iik7WXW8",
                        "y":"cXKzcH2gtOyTBQvnLuyTz6I-qWqnS8MQnFCkhWVzojM"})
issuer_DID = didkit.key_to_did("ethr", issuer_key)
print('issuer DID = ', issuer_DID)

OFFER_DELAY = timedelta(seconds= 10*60)
CREDENTIAL_EXPIRATION_DELAY = timedelta(seconds= 365*24*60*60) # 1 year


# Display QR code for wallet
@app.route('/' , methods=['GET'], defaults={'red' : red}) 
def qrcode(red) :
    # loading of the JSON-LD verifiable credential we use for this demo
    # see https://www.w3.org/TR/vc-data-model/ 
    credential = json.load(open('LearningAchievement.jsonld', 'r'))
    credential["issuer"] = issuer_DID
    credential['issuanceDate'] = datetime.now().replace(microsecond=0).isoformat() + "Z"
    credential['expirationDate'] = (datetime.now() +  CREDENTIAL_EXPIRATION_DELAY).replace(microsecond=0).isoformat() + "Z"
    credential['id'] = "urn:uuid:" + str(uuid.uuid4())
    credential['issuanceDate'] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    credentialOffer = {
            "type": "CredentialOffer",
            "credentialPreview": credential,
            "expires" : (datetime.now() + OFFER_DELAY).replace(microsecond=0).isoformat() + "Z",
            "shareLink" : "",
            "display" : { "backgroundColor" : "ffffff"}
        }
    # this url is displayed through the QR code
    # credential id is is used for the dynamic endpoint but one coud use another random
    url = 'http://192.168.0.231:3000/endpoint/' + credential['id'] + '?issuer=' + issuer_DID
    
    # session data stored with Redis
    red.set(credential['id'], json.dumps(credentialOffer))
    # html page. the window event is used to switch when the credential has been transfered
    html_string = """  <!DOCTYPE html>
        <html>
        <head></head>
        <body>
        <div>  
            <h2>Scan the QRCode bellow with your Talao wallet.</h2> 
            <br>  
            <div><img src="{{ qrcode(url) }}" ></div>
        </div>
        <script>
            var source = new EventSource('/issuer_stream');
            source.onmessage = function (event) {
                const result = JSON.parse(event.data)
                if (result.check == 'success' & result.id == '{{id}}'){
                window.location.href="/credentialOffer_back";
            }
        };
        </script>
        </body>
        </html>
        """
    return render_template_string(html_string,
                                url=url,
                                id=credential['id'],
                                )

# Endpoint for wallet call, it is a dynamic endpoint path
@app.route('/endpoint/<id>', methods = ['GET', 'POST'],  defaults={'red' : red})
def credentialOffer_endpoint(id, red):
    try : 
        credentialOffer = red.get(id).decode()
    except :
        return jsonify('Redis server error'), 500

    if request.method == 'GET':
        return Response(json.dumps(credentialOffer, separators=(':', ':')),
                        headers={ "Content-Type" : "application/json"},
                        status=200)
                       
    if request.method == 'POST':
        credential =  json.loads(credentialOffer)['credentialPreview']
        red.delete(id)
     
        # wallet DID  (user DID) is provided by wallet as "subject_id"
        credential['credentialSubject']['id'] = request.form['subject_id']
     
        # issuer signs the verifiable cerdential
        # options : https://www.w3.org/TR/did-core/#verification-methods
        didkit_options = {
            "proofPurpose": "assertionMethod",
            "verificationMethod": didkit.key_to_verification_method("ethr", issuer_key)
            }
        signed_credential =  didkit.issue_credential(json.dumps(credential),
                                                     didkit_options.__str__().replace("'", '"'),
                                                     issuer_key )
        data = json.dumps({
                            'id' : id,
                            'check' : 'success',
                            })
        red.publish('issuer', data)
        
        return Response(json.dumps(signed_credential, separators=(':', ':')),
                        headers={ "Content-Type" : "application/json"},
                        status=200)

# followup screen when  wallet has received verfiable cerdential
@app.route('/credentialOffer_back', methods = ['GET'])
def credentialOffer_back():
    html_string = """
        <!DOCTYPE html>
        <html>
        <body class="h-screen w-screen flex ">
        <p></p>
        <h2>Verifiable Credential has been signed and transfered to wallet"</h2<
        <br><br><br>
        <form action="/playground" method="GET" >
                    <button  type"submit" >Back</button></form>
        </body>
        </html>"""
    return render_template_string(html_string)


# server event push for user agent EventSource / websocket is anothere solution
@app.route('/issuer_stream', methods = ['GET', 'POST'],  defaults={'red' : red})
def offer_stream(red):
    def event_stream(red):
        pubsub = red.pubsub()
        pubsub.subscribe('issuer')
        for message in pubsub.listen():
            if message['type']=='message':
                yield 'data: %s\n\n' % message['data'].decode()  
    headers = { "Content-Type" : "text/event-stream",
                "Cache-Control" : "no-cache",
                "X-Accel-Buffering" : "no"}
    return Response(event_stream(red), headers=headers)



# MAIN entry point. Flask http server
if __name__ == '__main__':
    app.run(host = "192.168.0.231", port= 3000, debug=True)