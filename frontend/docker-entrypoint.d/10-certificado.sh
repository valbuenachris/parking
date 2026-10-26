#!/bin/sh
# Genera un certificado autofirmado de desarrollo al arrancar el contenedor si
# no existe ya en el volumen de certificados. Así la clave privada no queda
# horneada en la imagen. En producción sustituye estos archivos por un
# certificado real montado en el mismo directorio.
set -e

CERT_DIR=/etc/nginx/certs
CERT_PUB="$CERT_DIR/fullchain.pem"
CERT_KEY="$CERT_DIR/privkey.pem"

if [ -s "$CERT_PUB" ] && [ -s "$CERT_KEY" ]; then
    exit 0
fi

echo "Generando certificado autofirmado de desarrollo en $CERT_DIR"
mkdir -p "$CERT_DIR"
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$CERT_KEY" \
    -out "$CERT_PUB" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
