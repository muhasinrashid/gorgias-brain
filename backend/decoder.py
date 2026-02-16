
import base64
encoded = "cmVuaWwubWF0aGV3c0BuZW9wcmF4aXMuaW46NTI5M2EzM2JhNjU5MjhhZjViMWQ0ZDMzZmRmZWFkZDhlMzY2ODQyYjBkM2UwZjJiNzcxNTg0MTBkMDYzMGRlZg=="
decoded = base64.b64decode(encoded).decode('utf-8')
with open("decoded.txt", "w") as f:
    f.write(decoded)
print(decoded)
