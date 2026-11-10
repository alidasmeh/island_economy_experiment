# project-template


When you made a copy of this repo, update the name of the project in the list of places below: 
- frontend/public/manifest.json => name, short_name
- frontend/package.json => name
- backend/pyproject.toml => name
- backend/.gitlab-ci.yml => APP_NAME, DATABASE_NAME, NAMESPACE 
- frontend/.gitlab-ci.yml => APP_NAME, BACKEND_URL, REACT_APP_BACKEND_URL, NAMESPACE
- frontend/.gitlab-ci.yml => build-stage-react.before_script -> REACT_APP_BACKEND_URL, REACT_APP_BACKEND_SOCKET_URL


Create a `.env` file in the same directory as `docker-compose.yml` file. Add following variables inside.
```
DATABASE_URL = 
REACT_APP_BACKEND_URL = 
REACT_APP_BACKEND_SOCKET_URL = 
```

# Create GitLab CI/CD variables
All the following variables should be added to GitLab CI/CD variables.

- APP_NAME_PREFIX
- DASHBOARD_USERNAME
- DASHBOARD_PASSWORD
- DATABASE_URL
- REACT_APP_BACKEND_SOCKET_URL
- REACT_APP_BACKEND_URL


# Create namespace
To create a new repository for a project you should make a namespace at Portainer based on [this document](https://mpib.atlassian.net/wiki/spaces/CP/pages/1545535494/Create+a+Portainer+namespace).

You should replace all `project-template-` in `.gitlab-ci.yaml` files with the namespace (do not for get `-` at the end of the namespace.)

# Create PostgreSQL DB
To create a new PostgreSQL DB for your project/experiment follow this: [Create a Postgres database](https://mpib.atlassian.net/wiki/spaces/CP/pages/1506770989/Create+a+Postgres+database)
After getting DB credentials from GWDG update `DATABASE_URL` in gitlab>Settings>CI/CD>Variables (If you cannot access it, ask IT support or research engineers.). 