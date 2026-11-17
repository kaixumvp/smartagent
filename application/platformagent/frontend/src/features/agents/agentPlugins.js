export function getAgentPlugins(config) {
  if (Array.isArray(config?.plugins)) return config.plugins;
  return (config?.tools || []).map((ref) => ({ type: 'tool', ref }));
}

