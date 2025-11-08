from cryptography.fernet import Fernet

# Generate a key (do this once and save the key for later)
key = Fernet.generate_key()
cipher = Fernet(key)
with open("key.txt", "wb") as f:
    f.write(key)
# # Encrypt text
# with open("transcript.txt", "r") as f:
#     text = f.read()
#     encrypted_text = cipher.encrypt(text.encode())
#     with open("transcript.txt.enc", "wb") as f:
#         f.write(encrypted_text)

# Decrypt text
with open("transcript.txt.enc", "rb") as f:
    encrypted_text = f.read()
    decrypted_text = cipher.decrypt(encrypted_text).decode()
    with open("transcript.txt1", "w") as f:
        f.write(decrypted_text)
