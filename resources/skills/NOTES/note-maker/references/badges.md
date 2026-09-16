# Badge Reference

Badges make the README scannable and visually identify the tech stack at a glance.

## Format

```
[![Label](https://img.shields.io/badge/Label-version-HEXCOLOR.svg?logo=logoname&logoColor=white)](URL)
```

Version ranges use `+` suffix: `3.11+`, `0.100+`, `2.0+`

If no SimpleIcons logo exists for a technology, omit the `?logo=` parameter entirely.

## Color and Logo Table

| Technology       | Color  | Logo name       |
|-----------------|--------|-----------------|
| Python          | 3776AB | python          |
| FastAPI         | 009688 | fastapi         |
| PostgreSQL      | 336791 | postgresql      |
| Redis           | DC382D | redis           |
| Docker          | 2496ED | docker          |
| Kubernetes      | 326CE5 | kubernetes      |
| React           | 61DAFB | react           |
| TypeScript      | 3178C6 | typescript      |
| Node.js         | 339933 | nodedotjs       |
| Go              | 00ADD8 | go              |
| Rust            | 000000 | rust            |
| AWS             | FF9900 | amazonaws       |
| GCP             | 4285F4 | googlecloud     |
| Terraform       | 844FBA | terraform       |
| GitHub Actions  | 2088FF | githubactions   |
| Nginx           | 009639 | nginx           |
| GraphQL         | E10098 | graphql         |
| MongoDB         | 47A248 | mongodb         |
| Kafka           | 231F20 | apachekafka     |
| Elasticsearch   | 005571 | elasticsearch   |
| pytest          | 0A9EDC | pytest          |
| Pydantic        | E92063 | pydantic        |
| SQLAlchemy      | D71F00 | *(none — omit `?logo=`)* |

## Placement rules

- Root README gets the full set relevant to the topic
- Directory READMEs get only the badges relevant to that section
- Group related badges on one line (e.g., all database badges together)
