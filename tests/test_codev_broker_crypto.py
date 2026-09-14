import json
import shutil
import subprocess

import pytest

from core.codev import broker_crypto as crypto
from core.codev.contracts import BrokerProof, BrowserPublicKey


def proof():
    return BrokerProof(pairing_id="pairing_" + "a" * 32, browser_session_id="browser_" + "b" * 32,
                       online_account_id="website-account-A", nonce="n" * 43,
                       timestamp_ms=1800000000000, signature="x" * 86)


def test_webcrypto_and_python_verify_each_others_exact_transcripts():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node WebCrypto interpreter unavailable")
    key = crypto.new_key()
    request = '{"instruction":"Review café 🌿", "files":[]}'
    metadata = proof()
    message = crypto.request_message("https://elysiaecobotics.com", "/v1/status", metadata, request)
    script = r"""
      let input=''; for await (const chunk of process.stdin) input+=chunk;
      const fixture=JSON.parse(input), utf8=new TextEncoder();
      const imported=await crypto.subtle.importKey('jwk',fixture.publicKey,{name:'ECDSA',namedCurve:'P-256'},false,['verify']);
      const valid=await crypto.subtle.verify({name:'ECDSA',hash:'SHA-256'},imported,Buffer.from(fixture.signature,'base64url'),utf8.encode(fixture.message));
      if(!valid) throw new Error('Python signature was not verified by WebCrypto');
      const keys=await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);
      const publicKey=await crypto.subtle.exportKey('jwk',keys.publicKey);
      const signature=await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},keys.privateKey,utf8.encode(fixture.message));
      process.stdout.write(JSON.stringify({publicKey:{kty:publicKey.kty,crv:publicKey.crv,x:publicKey.x,y:publicKey.y},signature:Buffer.from(signature).toString('base64url')}));
    """
    result = subprocess.run([node, "--input-type=module", "-e", script],
                            input=json.dumps({"publicKey": crypto.public_key(key).model_dump(),
                                              "message": message.decode(), "signature": crypto.sign(key, message)}),
                            text=True, capture_output=True, timeout=10, check=True)
    returned = json.loads(result.stdout)
    browser_key = BrowserPublicKey.model_validate(returned["publicKey"])
    assert crypto.verify(browser_key, message, returned["signature"])
    for changed in [message + b" ", message.replace(b"website-account-A", b"website-account-B"),
                    message.replace(b"/v1/status", b"/v1/grants/share"),
                    message.replace(b"https://elysiaecobotics.com", b"https://www.elysiaecobotics.com")]:
        assert not crypto.verify(browser_key, changed, returned["signature"])


def test_response_signature_is_bound_to_the_initiating_request():
    key = crypto.new_key()
    metadata = proof()
    message = crypto.response_message("https://elysiaecobotics.com", "/v1/status", metadata,
                                      '{"input":1}', '{"workspace_grants":[]}')
    signature = crypto.sign(key, message)
    assert crypto.verify(crypto.public_key(key), message, signature)
    other = crypto.response_message("https://elysiaecobotics.com", "/v1/status",
                                    metadata.model_copy(update={"nonce": "y" * 43}),
                                    '{"input":1}', '{"workspace_grants":[]}')
    assert not crypto.verify(crypto.public_key(key), other, signature)
    assert not crypto.verify(crypto.public_key(crypto.new_key()), message, signature)
    assert not crypto.verify(crypto.public_key(key), message, signature + "=")
    with pytest.raises(ValueError, match="transcript"):
        crypto.request_message("https://elysiaecobotics.com\nPOST", "/v1/status", metadata, "{}")


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}', '{"value":NaN}', '[]', 'null'])
def test_ambiguous_or_nonobject_payloads_are_rejected(text):
    with pytest.raises(ValueError):
        crypto.strict_json(text)


def test_invalid_curve_coordinates_are_rejected():
    invalid = BrowserPublicKey(x=crypto.encode64(bytes(32)), y=crypto.encode64(bytes(32)))
    with pytest.raises(ValueError):
        crypto.load_public(invalid)
