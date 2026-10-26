#!/bin/sh
# Verifica el certificado autofirmado que se genera en runtime:
#  1) que incluye el SAN esperado (localhost + loopback) para que navegador y CI
#     lo acepten;
#  2) que en producción NO se genera un autofirmado (falla cerrada).
set -e

DIR_SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENTRYPOINT="$DIR_SCRIPT/../docker-entrypoint.d/10-certificado.sh"

DIR=$(mktemp -d)
trap 'rm -rf "$DIR"' EXIT

CERT_DIR="$DIR" PARQUEADERO_ENTORNO=desarrollo sh "$ENTRYPOINT"

openssl x509 -in "$DIR/fullchain.pem" -noout -ext subjectAltName > "$DIR/san.txt"
cat "$DIR/san.txt"
grep -q "DNS:localhost" "$DIR/san.txt"
grep -q "IP Address:127.0.0.1" "$DIR/san.txt"

DIR2=$(mktemp -d)
if CERT_DIR="$DIR2" PARQUEADERO_ENTORNO=produccion sh "$ENTRYPOINT" 2>/dev/null; then
    echo "ERROR: en producción no debe generarse un certificado autofirmado" >&2
    rm -rf "$DIR2"
    exit 1
fi
rm -rf "$DIR2"

echo "Certificado de runtime verificado (SAN correcto y guarda de producción activa)"
