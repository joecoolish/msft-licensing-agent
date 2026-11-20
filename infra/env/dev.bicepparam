using '../main.bicep'

param environmentName = 'dev'
param location = readEnvironmentVariable('AZURE_LOCATION', readEnvironmentVariable('AZURE_CLOUD', 'AzureCloud') == 'AzureUSGovernment' ? 'usgovvirginia' : 'eastus2')
param namePrefix = readEnvironmentVariable('NAME_PREFIX', 'licensing')
param tags = { application: 'licensing-agent', managedBy: 'bicep' }
param deployPrincipalId = readEnvironmentVariable('DEPLOY_PRINCIPAL_ID')
param apiAppIdUri = readEnvironmentVariable('API_APP_ID_URI')
param skuName = readEnvironmentVariable('AZURE_CLOUD', 'AzureCloud') == 'AzureUSGovernment' ? 'Standard' : 'GlobalStandard'
