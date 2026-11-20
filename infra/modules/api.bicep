import { roles } from '../roles.bicep'
param location string
param tags object
param stem string
param apiImage string
param apiAppIdUri string
param projectEndpoint string
param modelDeploymentName string
param cosmosEndpoint string
param workspaceId string
param appInsightsConnectionString string

var placeholder = apiImage == 'docker.io/library/nginx:1.28-alpine'
var probes = [
  for probeType in ['Startup', 'Readiness', 'Liveness']: {
    type: probeType
    httpGet: { path: '/healthz', port: placeholder ? 80 : 8000, scheme: 'HTTP' }
    initialDelaySeconds: 5
    periodSeconds: 10
    timeoutSeconds: 2
    failureThreshold: probeType == 'Startup' ? 30 : 3
  }
]
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${stem}-api'
  location: location
  tags: tags
}
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: replace('acr${stem}', '-', '')
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}
resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identity.id, roles.acrPull)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}
resource containerEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: 'cae-${stem}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: { destination: 'azure-monitor' }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
  }
}
resource logs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: containerEnvironment
  name: 'log-analytics'
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'ContainerAppConsoleLogs', enabled: true }
      { category: 'ContainerAppSystemLogs', enabled: true }
    ]
  }
}
resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'api'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: containerEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: placeholder ? 80 : 8000
        transport: 'auto'
      }
      registries: [
        { server: registry.properties.loginServer, identity: identity.id }
      ]
    }
    template: {
      containers: [
        union({
          name: 'api'
          image: apiImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'AZURE_AUTHORITY_HOST', value: environment().authentication.loginEndpoint }
            { name: 'AZURE_CLOUD', value: environment().name }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: projectEndpoint }
            { name: 'MODEL_DEPLOYMENT_NAME', value: modelDeploymentName }
            { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'COSMOS_DATABASE', value: 'appstate' }
            { name: 'API_APP_ID_URI', value: apiAppIdUri }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'LOG_CONTENT', value: 'false' }
          ]
          probes: probes
        }, placeholder ? {
          command: ['/bin/sh', '-c']
          args: ['printf healthy > /usr/share/nginx/html/healthz; exec nginx -g "daemon off;"']
        } : {})
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [pull]
}
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
output acrLoginServer string = registry.properties.loginServer
output containerAppName string = app.name
output apiUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
