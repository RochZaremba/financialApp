FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web apps/web
ENV API_INTERNAL_URL=http://api:8000
RUN rm -rf apps/web/public/demo && npm run build
FROM node:22-alpine
ENV NODE_ENV=production API_INTERNAL_URL=http://api:8000
WORKDIR /app
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/apps/web ./apps/web
USER node
EXPOSE 3000
CMD ["npm","run","start","--workspace","apps/web"]
