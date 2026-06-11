"""Compatibilidade com o comando antigo `python server.py`.

A aplicacao principal agora fica em main.py e usa os modulos em modules/.
"""

from main import app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
