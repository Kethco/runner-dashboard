# Stage 1: Build the application
FROM node:20-slim AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

FROM base AS build
COPY . /usr/src/app
WORKDIR /usr/src/app

# NEW: This forces pnpm to resolve versions directly and ignores the "catalog:" protocol
RUN pnpm config set resolution-mode highest
RUN pnpm install --no-frozen-lockfile --shamefully-hoist

# Build the specific dashboard project
RUN pnpm --filter runner-dashboard build

# Stage 2: Serve the application using Nginx
FROM nginx:alpine
# Copy the build output to the Nginx html folder
COPY --from=build /usr/src/app/artifacts/runner-dashboard/dist /usr/share/nginx/html

# Expose port 8080 (Cloud Run's default)
EXPOSE 8080
# Configure Nginx to listen on 8080
RUN sed -i 's/listen\(.*\)80;/listen 8080;/' /etc/nginx/conf.d/default.conf

CMD ["nginx", "-g", "daemon off;"]
