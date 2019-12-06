#!/usr/bin/env python
import json
import os
import requests
import sys


### you will likely prefer to use environment variables ###
### however you can edit these if you prefer ###

# URL to acme-dns instance
ACMEDNS_URL = os.environ.get("ACMEDNSAUTH_URL", None)
# used to maintain compatibility across future versions
ENV_VERSION = os.environ.get("ACMEDNSAUTH_ENV_VERSION", None)
# Path for acme-dns credential storage
STORAGE_PATH = os.environ.get("ACMEDNSAUTH_STORAGE_PATH",
                              "/etc/letsencrypt/acmedns.json")
# Whitelist for address ranges to allow the updates from
# Example: ALLOW_FROM = ["192.168.10.0/24", "::1/128"]
# if customized on the commandline, this must be a list encoded as a json string
# Example: `export ACMEDNSAUTH_ALLOW_FROM='["192.168.10.0/24", "::1/128"]'`
ALLOW_FROM = os.environ.get("ACMEDNSAUTH_ALLOW_FROM", [])
# Force re-registration. Overwrites the already existing acme-dns accounts.
FORCE_REGISTER = os.environ.get("ACMEDNSAUTH_FORCE_REGISTER", False)


###   DO NOT EDIT BELOW THIS POINT   ###
###         HERE BE DRAGONS          ###


class AcmeDnsClient(object):
    """
    Handles the communication with ACME-DNS API
    """

    def __init__(self, acmedns_url):
        self.acmedns_url = acmedns_url

    def register_account(self, allowfrom):
        """Registers a new ACME-DNS account"""

        if allowfrom:
            # Include whitelisted networks to the registration call
            reg_data = {"allowfrom": allowfrom}
            res = requests.post(self.acmedns_url+"/register",
                                data=json.dumps(reg_data))
        else:
            res = requests.post(self.acmedns_url+"/register")
        if res.status_code == 201:
            # The request was successful
            return res.json()
        else:
            # Encountered an error
            msg = ("Encountered an error while trying to register a new acme-dns "
                   "account. HTTP status {}, Response body: {}")
            print(msg.format(res.status_code, res.text))
            sys.exit(1)

    def update_txt_record(self, account, txt):
        """Updates the TXT challenge record to ACME-DNS subdomain."""
        update = {"subdomain": account['subdomain'], "txt": txt}
        headers = {"X-Api-User": account['username'],
                   "X-Api-Key": account['password'],
                   "Content-Type": "application/json"}
        res = requests.post(self.acmedns_url+"/update",
                            headers=headers,
                            data=json.dumps(update))
        if res.status_code == 200:
            # Successful update
            return
        else:
            msg = ("Encountered an error while trying to update TXT record in "
                   "acme-dns. \n"
                   "------- Request headers:\n{}\n"
                   "------- Request body:\n{}\n"
                   "------- Response HTTP status: {}\n"
                   "------- Response body: {}")
            s_headers = json.dumps(headers, indent=2, sort_keys=True)
            s_update = json.dumps(update, indent=2, sort_keys=True)
            s_body = json.dumps(res.json(), indent=2, sort_keys=True)
            print(msg.format(s_headers, s_update, res.status_code, s_body))
            sys.exit(1)

class Storage(object):
    def __init__(self, storagepath):
        self.storagepath = storagepath
        self._data = self.load()

    def load(self):
        """Reads the storage content from the disk to a dict structure"""
        data = dict()
        filedata = ""
        try:
            with open(self.storagepath, 'r') as fh:
                filedata = fh.read()
        except IOError as e:
            if os.path.isfile(self.storagepath):
                # Only error out if file exists, but cannot be read
                print("ERROR: Storage file exists but cannot be read")
                sys.exit(1)
        try:
            data = json.loads(filedata)
        except ValueError:
            if len(filedata) > 0:
                # Storage file is corrupted
                print("ERROR: Storage JSON is corrupted")
                sys.exit(1)
        return data

    def save(self):
        """Saves the storage content to disk"""
        serialized = json.dumps(self._data)
        try:
            with os.fdopen(os.open(self.storagepath,
                                   os.O_WRONLY | os.O_CREAT, 0o600), 'w') as fh:
                fh.truncate()
                fh.write(serialized)
        except IOError as e:
            print("ERROR: Could not write storage file.")
            sys.exit(1)

    def put(self, key, value):
        """Puts the configuration value to storage and sanitize it"""
        # If wildcard domain, remove the wildcard part as this will use the
        # same validation record name as the base domain
        if key.startswith("*."):
            key = key[2:]
        self._data[key] = value

    def fetch(self, key):
        """Gets configuration value from storage"""
        try:
            return self._data[key]
        except KeyError:
            return None


def template_new(env_version):
    templated = """
# ---------- CUSTOMIZE THE BELOW ----------

# required settings
#
# URL to acme-dns instance
export ACMEDNSAUTH_URL="https://acme-dns.example.com"
# used to maintain compatibility across future versions
export ACMEDNSAUTH_ENV_VERSION="%(env_version)s"

# optional settings
#
# Path for acme-dns credential storage
export ACMEDNSAUTH_STORAGE_PATH="/etc/letsencrypt/acmedns.json"
# Whitelist for address ranges to allow the updates from
# this must be a list encoded as a json string
# Example: `export ACMEDNSAUTH_ALLOW_FROM='["192.168.10.0/24", "::1/128"]'`
export ACMEDNSAUTH_ALLOW_FROM='[]'
# Force re-registration. Overwrites the already existing acme-dns accounts.
export ACMEDNSAUTH_FORCE_REGISTER="False"

# ----------                     ----------
""" % {'env_version': env_version, }
    print(templated)


if __name__ == "__main__":

    # this may be used in the future to handle compatibility concerns
    ENV_VERSION__CURRENT = 1
    ENV_VERSION__MINMAX = (1, 1)

    if len(sys.argv) == 2:
        if sys.argv[1] == '--version':
            print("The current ENV_VERSION/ACMEDNSAUTH_ENV_VERSION is: %s" % ENV_VERSION__CURRENT)
            print("This script is compatible with versions: %s-%s" % ENV_VERSION__MINMAX)
            sys.exit(1)
        if sys.argv[1] == '--setup':
            template_new(ENV_VERSION__CURRENT)
            sys.exit(1)

    # validation/coercion : BEGIN
    if not ACMEDNS_URL:
        raise ValueError("`ACMEDNS_URL` or the environment variable "
                         "`ACMEDNSAUTH_URL` must be set")
    if ENV_VERSION is None:
        raise ValueError("`ENV_VERSION` or the environment variable "
                         "`ACMEDNSAUTH_ENV_VERSION` must be set. "
                         "The current version is %s" % ENV_VERSION__CURRENT)
    ENV_VERSION = int(ENV_VERSION)
    if not isinstance(ALLOW_FROM, list):
        try:
            ALLOW_FROM = json.loads(ALLOW_FROM)
            if not isinstance(ALLOW_FROM, list):
                raise ValueError()
        except:
            raise ValueError("ALLOW_FROM must be a list")
    if not isinstance(FORCE_REGISTER, bool):
        if FORCE_REGISTER.lower() in ('true', '1'):
            FORCE_REGISTER = True
        else:
            FORCE_REGISTER = False
    # validation/coercion : END

    # resume original script
    DOMAIN = os.environ["CERTBOT_DOMAIN"]
    if DOMAIN.startswith("*."):
        DOMAIN = DOMAIN[2:]
    VALIDATION_DOMAIN = "_acme-challenge."+DOMAIN
    VALIDATION_TOKEN = os.environ["CERTBOT_VALIDATION"]

    # Init
    client = AcmeDnsClient(ACMEDNS_URL)
    storage = Storage(STORAGE_PATH)

    # Check if an account already exists in storage
    account = storage.fetch(DOMAIN)
    if FORCE_REGISTER or not account:
        # Create and save the new account
        account = client.register_account(ALLOW_FROM)
        storage.put(DOMAIN, account)
        storage.save()

        # Display the notification for the user to update the main zone
        msg = "Please add the following CNAME record to your main DNS zone:\n{}"
        cname = "{} CNAME {}.".format(VALIDATION_DOMAIN, account["fulldomain"])
        print(msg.format(cname))

    # Update the TXT record in acme-dns instance
    client.update_txt_record(account, VALIDATION_TOKEN)
