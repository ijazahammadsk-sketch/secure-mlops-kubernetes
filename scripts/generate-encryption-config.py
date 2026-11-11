from pathlib import Path
import base64
import secrets

out = Path("encryption/encryption-config.yaml")
out.parent.mkdir(parents=True, exist_ok=True)
key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
content = f"""apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: {key}
      - identity: {{}}
"""
out.write_text(content, encoding="utf-8")
print(f"Created {out}")
print("Keep this file private. Back it up securely; losing the key can make stored Secrets unreadable.")
