# Image Python officielle légère (aucune librairie externe à installer)
FROM python:3.11-slim

# Dossier de travail dans le conteneur
WORKDIR /app

# Empêche Python de créer des fichiers .pyc et affiche les logs en direct
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Configuration réseau et persistance SQLite dans le conteneur :
# - 0.0.0.0 permet d'accepter les connexions venant de l'extérieur du conteneur
# - /app/data/caloria.db sera monté sur un volume persistant pour ne jamais perdre les repas
ENV CALORIA_HOST=0.0.0.0
ENV CALORIA_PORT=8000
ENV CALORIA_DB_PATH=/app/data/caloria.db

# Copie les fichiers de l'application dans le conteneur
COPY . .

# Crée le dossier dédié à la base SQLite persistante
RUN mkdir -p /app/data

# Port exposé par le serveur Python
EXPOSE 8000

# Lance le serveur web CalorIA
CMD ["python3", "app.py"]
