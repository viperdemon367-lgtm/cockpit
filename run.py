"""Lance Cockpit : python run.py (ou double-clic sur le .exe). Ouvre http://localhost:8765"""
import socket
import sys
import threading
import webbrowser

URL = "http://localhost:8765"


def port_in_use(port=8765):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    if port_in_use():
        # déjà lancé : on ouvre simplement le navigateur
        webbrowser.open(URL)
        return
    import uvicorn

    from app.server import app

    print("Cockpit tourne sur", URL)
    print("Garde cette fenêtre ouverte pendant que tu utilises l'outil. Ferme-la pour l'arrêter.")
    threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # message lisible au lieu d'une fenêtre qui se ferme
        print("Erreur au démarrage :", e)
        if getattr(sys, "frozen", False):
            input("Appuie sur Entrée pour fermer…")
        raise
