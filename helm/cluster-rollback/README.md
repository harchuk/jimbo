# Cluster Rollback Helm Chart

## Быстрый старт

```sh
helm install cluster-rollback ./helm/cluster-rollback --create-namespace --namespace cluster-rollback
```

## Параметры values.yaml
- `namespace` — namespace для деплоя
- `image.repository` — docker-образ
- `image.tag` — тег образа
- `service.type` — тип сервиса (ClusterIP/NodePort/LoadBalancer)
- `service.port` — порт сервиса
- `service.targetPort` — порт контейнера
- `replicaCount` — количество реплик

## Что разворачивается
- Namespace
- ServiceAccount
- ClusterRole/ClusterRoleBinding
- Deployment
- Service

## Пример доступа к UI

```sh
kubectl port-forward svc/cluster-rollback 8080:80 -n cluster-rollback
# Открыть http://localhost:8080
``` 