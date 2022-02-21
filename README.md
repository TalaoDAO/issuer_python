# issuer_python
Example of a simple SSI issuer for the Talao wallet

mkdir myproject
cd myproject
python3 -m venv venv
. venv/bin/activate

pip install redis
pip install flask-session
pip install didkit==0.2.1


git clone https://github.com/TalaoDAO/issuer_python.git

Run

python issuer.py

The verifiable credential is in a JSON-LD format

Main source is issuer.py
