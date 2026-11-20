param location string
param tags object
param stem string
param accountName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${stem}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}
resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${stem}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = { name: accountName }
// The official Foundry AppInsights connection expects a service-derived connection
// string, not an Azure credential. No user secret is stored in source or workflows.
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: account
  name: 'application-insights'
  properties: {
    category: 'AppInsights'
    target: insights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: { key: insights.properties.ConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: insights.id }
  }
}
output workspaceId string = workspace.id
output connectionString string = insights.properties.ConnectionString
