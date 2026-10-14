FROM node:22-alpine AS build

WORKDIR /app

COPY platformagent/frontend/package.json platformagent/frontend/package-lock.json ./
RUN npm ci

COPY platformagent/frontend/ ./
RUN npm run build

FROM nginx:alpine

COPY platformagent/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
