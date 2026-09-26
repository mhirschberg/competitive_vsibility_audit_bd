FROM node:22-alpine AS build
WORKDIR /web
COPY package*.json ./
RUN npm ci
COPY . ./

# Every build input below is deliberately public. No server-side key belongs
# in this image or in the browser's generated config.json.
ARG SUPABASE_URL
ARG PUBLIC_SUPABASE_TOKEN
ARG AUDIT_API_URL
ARG WORKSHOP_ID
RUN SUPABASE_PUBLISHABLE_KEY="$PUBLIC_SUPABASE_TOKEN" npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
