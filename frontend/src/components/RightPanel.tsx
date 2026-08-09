interface RightPanelProps {
  selectedThreat: string | null;
}

export default function RightPanel({ selectedThreat }: RightPanelProps) {
  const threatDetails: Record<string, any> = {
    'threat-1': {
      id: 'threat-1',
      name: 'Suspicious Token Transfer',
      severity: 'CRITICAL',
      address: '0x742d35Cc6634C0532925a3b844Bc91e6a39e3fa3',
      riskScore: 92,
      lastSeen: '2 minutes ago',
      chain: 'Ethereum',
      actions: [
        'Add to blacklist',
        'Monitor address',
        'View full report',
        'Track on-chain activity',
      ],
      description: 'Detected unusual token movement pattern matching known exploit signatures.',
      impactedAddresses: 1247,
    },
    'threat-2': {
      id: 'threat-2',
      name: 'Flash Loan Attack Pattern',
      severity: 'HIGH',
      address: '0x1234567890123456789012345678901234567890',
      riskScore: 78,
      lastSeen: '15 minutes ago',
      chain: 'Polygon',
      actions: [
        'Monitor activity',
        'Set alerts',
        'View transaction log',
      ],
      description: 'Identified potential flash loan attack sequence detected.',
      impactedAddresses: 342,
    },
    'threat-3': {
      id: 'threat-3',
      name: 'Bridge Exploit Detection',
      severity: 'HIGH',
      address: '0xabcdefabcdefabcdefabcdefabcdefabcdefabcd',
      riskScore: 85,
      lastSeen: '45 minutes ago',
      chain: 'Base',
      actions: [
        'Quarantine address',
        'View evidence',
        'Alert network',
      ],
      description: 'Cross-chain bridge interaction flagged for suspicious behavior.',
      impactedAddresses: 892,
    },
  };

  const threat = selectedThreat && threatDetails[selectedThreat];

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
        return 'text-neon-pink bg-neon-pink/10';
      case 'HIGH':
        return 'text-neon-amber bg-neon-amber/10';
      case 'MEDIUM':
        return 'text-neon-blue bg-neon-blue/10';
      case 'LOW':
        return 'text-neon-green bg-neon-green/10';
      default:
        return 'text-cyber-400 bg-cyber-800/50';
    }
  };

  const getRiskScoreColor = (score: number) => {
    if (score >= 80) return 'text-neon-pink';
    if (score >= 60) return 'text-neon-amber';
    if (score >= 40) return 'text-neon-blue';
    return 'text-neon-green';
  };

  return (
    <div className="w-80 bg-cyber-900 border-l border-cyber-700/50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-cyber-700/50">
        <h2 className="text-lg font-bold text-white">Threat Details</h2>
        <p className="text-sm text-cyber-400 mt-1">
          {selectedThreat ? 'Selected threat information' : 'Select a threat to view details'}
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {threat ? (
          <div className="p-6 space-y-6">
            {/* Threat Name */}
            <div>
              <h3 className="text-xl font-bold text-white mb-2">{threat.name}</h3>
              <div className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${getSeverityColor(threat.severity)}`}>
                {threat.severity}
              </div>
            </div>

            {/* Risk Score */}
            <div>
              <div className="text-sm text-cyber-400 mb-2">Risk Score</div>
              <div className="flex items-end gap-3">
                <div className={`text-4xl font-bold ${getRiskScoreColor(threat.riskScore)}`}>
                  {threat.riskScore}
                </div>
                <div className="text-sm text-cyber-400 mb-1">/ 100</div>
              </div>
              <div className="w-full bg-cyber-800 rounded-full h-2 mt-2 overflow-hidden">
                <div
                  className={`h-full ${threat.riskScore >= 80 ? 'bg-neon-pink' : threat.riskScore >= 60 ? 'bg-neon-amber' : 'bg-neon-blue'}`}
                  style={{ width: `${threat.riskScore}%` }}
                ></div>
              </div>
            </div>

            {/* Details */}
            <div className="space-y-3 bg-cyber-800/50 rounded-lg p-4">
              <div>
                <div className="text-xs text-cyber-400 uppercase tracking-wider mb-1">Address</div>
                <div className="font-mono text-sm text-neon-blue break-all">{threat.address}</div>
              </div>
              <div>
                <div className="text-xs text-cyber-400 uppercase tracking-wider mb-1">Chain</div>
                <div className="text-cyber-200">{threat.chain}</div>
              </div>
              <div>
                <div className="text-xs text-cyber-400 uppercase tracking-wider mb-1">Last Seen</div>
                <div className="text-cyber-200">{threat.lastSeen}</div>
              </div>
              <div>
                <div className="text-xs text-cyber-400 uppercase tracking-wider mb-1">Impacted Addresses</div>
                <div className="text-cyber-200">{threat.impactedAddresses.toLocaleString()}</div>
              </div>
            </div>

            {/* Description */}
            <div>
              <div className="text-sm text-cyber-400 mb-2">Description</div>
              <p className="text-sm text-cyber-300 leading-relaxed">{threat.description}</p>
            </div>

            {/* Actions */}
            <div className="space-y-2 pt-4 border-t border-cyber-700/50">
              {threat.actions.map((action: string, idx: number) => (
                <button
                  key={idx}
                  className="w-full px-4 py-2 rounded-lg text-sm font-medium bg-cyber-800/50 text-cyber-300 hover:bg-neon-blue/20 hover:text-neon-blue border border-cyber-700/50 hover:border-neon-blue/50 transition-all"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-center px-6">
            <div>
              <div className="text-5xl mb-4">🛡️</div>
              <p className="text-cyber-400">No threat selected</p>
              <p className="text-sm text-cyber-500 mt-2">Click on a threat card to view details</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
