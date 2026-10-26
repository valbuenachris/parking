FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine
# openssl se usa en tiempo de arranque para generar el certificado autofirmado de
# desarrollo dentro del volumen de certificados; la clave privada nunca queda
# horneada en una capa de la imagen. En producción monta un certificado real en
# /etc/nginx/certs (fullchain.pem + privkey.pem) y sobrescríbelo.
RUN apk add --no-cache openssl
COPY docker-entrypoint.d/ /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/10-certificado.sh
# El nginx oficial procesa *.template con envsubst al arrancar, sustituyendo solo
# las variables de entorno (p. ej. PARQUEADERO_HSTS) y respetando las de nginx.
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 443
