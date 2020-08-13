import importlib
afy_spec = importlib.util.find_spec("afy")
afy_found = afy_spec is not None
if afy_found:
    from afy.afy_flask import app
else:
    from afy_flask import app

if __name__ == "__main__":
    app.run()