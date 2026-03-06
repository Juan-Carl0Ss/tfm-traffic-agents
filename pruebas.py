import undetected_chromedriver as uc

driver = uc.Chrome(
    driver_executable_path=r"C:\Users\juanc\Desktop\tfm\chromedriver.exe",
    browser_executable_path=r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    options=uc.ChromeOptions()
)

driver.get("https://www.google.com")


import json, time, pathlib, concurrent.futures as cf
import socket, errno, sys, os, logging, yaml, paramiko, csv, datetime, html
from paramiko.ssh_exception import AuthenticationException, SSHException, NoValidConnectionsError, BadHostKeyException

ip = "
port = 22
user = "testuser"
password = "testpassword"
keyfile = None
allow_agent = True
look_for_keys = True



client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

def _connect_with_prefs(client, ip, port, user, password, keyfile, allow_agent, look_for_keys):
    client.connect(
        ip, port=port, username=user, password=password, key_filename=keyfile,
        timeout=8, allow_agent=allow_agent, look_for_keys=look_for_keys, compress=True
    )

try:
    try:
        _connect_with_prefs(client, ip, port, user, password, keyfile, allow_agent, look_for_keys)
    except SSHException as e:
        if "Incorrect padding" in str(e):
            _connect_with_prefs(client, ip, port, user, password, keyfile, False, False)
       
       
       
except AuthenticationException as e:
    result["ok"] = False
    result["errors"].append({"connect": "AUTH_FAIL", "detail": str(e)})
    ...
