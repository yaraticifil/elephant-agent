import React, { useState, useEffect, useRef } from 'react';
import { Shield, Brain, Zap, Search, Eye, AlertTriangle, FileText, Cpu, Server, Fingerprint, Crosshair, Terminal, Network, Activity, Globe } from 'lucide-react';

const OPERATIONAL_KEYWORDS = ['dal', 'saldır', 'sansürsüz', 'hızlı', 'yok et', 'yerel', 'gizli', 'infaz', 'shadow', 'mistral'];

// 15 Agents mapping to specific icons and orbit positions (radius % of arena, angle in degrees)
// Angles distributed nicely around the 360 circle. 
// Inner orbit (R=22.5% of arena), Outer orbit (R=42.5% of arena)
const AGENT_CONFIG = {
  gatekeeper:   { icon: Shield,     orbit: 'inner', angle: 0 },
  planner:      { icon: Brain,      orbit: 'inner', angle: 45 },
  mask:         { icon: Fingerprint,orbit: 'inner', angle: 90 },
  shadow:       { icon: Crosshair,  orbit: 'inner', angle: 135 },
  executor:     { icon: Zap,        orbit: 'inner', angle: 180 },
  auditor:      { icon: Eye,        orbit: 'inner', angle: 225 },
  memory_agent: { icon: Server,     orbit: 'inner', angle: 270 },
  watchdog:     { icon: AlertTriangle, orbit: 'inner', angle: 315 },
  
  researcher:   { icon: Search,     orbit: 'outer', angle: 30 },
  creator:      { icon: FileText,   orbit: 'outer', angle: 80 },
  critic:       { icon: Activity,   orbit: 'outer', angle: 130 },
  reporter:     { icon: Terminal,   orbit: 'outer', angle: 180 },
  visual:       { icon: Eye,        orbit: 'outer', angle: 230 },
  listener:     { icon: Network,    orbit: 'outer', angle: 280 },
  speaker:      { icon: Globe,      orbit: 'outer', angle: 330 },
};

export default function App() {
  const [input, setInput] = useState('');
  const [theme, setTheme] = useState('strategic');
  const [logs, setLogs] = useState([]);
  const [agents, setAgents] = useState({});
  const [activeSpeech, setActiveSpeech] = useState({});
  const logsEndRef = useRef(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    const eventSource = new EventSource('http://localhost:8000/stream');

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const timestamp = new Date().toLocaleTimeString('tr-TR', { hour12: false });
        const sender = data.sender_agent;
        
        if (sender && sender !== 'orchestrator') {
          setAgents(prev => ({
            ...prev,
            [sender]: { lastSeen: Date.now(), status: data.payload?.status || 'active' }
          }));

          // Trigger waveform / activity flash for 2 seconds
          setActiveSpeech(prev => ({ ...prev, [sender]: true }));
          setTimeout(() => {
            setActiveSpeech(prev => ({ ...prev, [sender]: false }));
          }, 2000);
        }

        if (msgType === 'speak.request') {
          const text = data.payload?.text;
          if (text) {
            const utterance = new SpeechSynthesisUtterance(text);
            // Detect if contains Turkish characters to pick a better voice
            utterance.lang = /[ığüşöçİĞÜŞÖÇ]/.test(text) ? 'tr-TR' : 'en-US';
            window.speechSynthesis.speak(utterance);
          }
        }

        if (msgType !== 'agent_heartbeat') { // filter spam
          let messageTxt = JSON.stringify(data.payload);
          if (msgType === 'task.created') messageTxt = `Directive established: ${data.payload.title}`;
          if (msgType === 'agent_task_request') messageTxt = `Processing intel routing...`;
          if (msgType === 'task_completed') messageTxt = `Execution confirmed. Output logged.`;
          
          setLogs(prev => [...prev.slice(-49), {
            id: data.message_id || Date.now() + Math.random(),
            time: timestamp,
            source: sender || 'THE CORE',
            type: msgType,
            msg: messageTxt
          }]);
        }
      } catch (err) {}
    };

    return () => eventSource.close();
  }, []);

  useEffect(() => {
    const lowerInput = input.toLowerCase();
    const isOperational = OPERATIONAL_KEYWORDS.some(k => lowerInput.includes(k));
    const newTheme = isOperational ? 'operational' : 'strategic';
    if (newTheme !== theme) {
      setTheme(newTheme);
      document.body.className = `theme-${newTheme}`;
    }
  }, [input, theme]);

  const handleExecute = async () => {
    if (!input.trim()) return;
    try {
      await fetch('http://localhost:8000/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: input,
          task_type: 'research',
          mode: theme === 'operational' ? 'attack' : 'work',
          assigned_agent: 'gatekeeper'
        })
      });
      setInput('');
      // Flash Core
      setActiveSpeech(prev => ({ ...prev, orchestrator: true }));
      setTimeout(() => setActiveSpeech(prev => ({ ...prev, orchestrator: false })), 2000);
    } catch (err) {
      console.error('Failed to dispatch task:', err);
    }
  };

  // Calculate positions for nodes in the arena
  // Arena is 100vh X 100vh max width
  const renderAgentNodes = () => {
    return Object.entries(AGENT_CONFIG).map(([name, conf]) => {
      const radiusPct = conf.orbit === 'inner' ? 22.5 : 42.5; 
      // convert polar to cartesian
      const theta = (conf.angle - 90) * (Math.PI / 180); // -90 so 0 is top
      const x = 50 + radiusPct * Math.cos(theta); // % from left
      const y = 50 + radiusPct * Math.sin(theta); // % from top

      const Icon = conf.icon;
      const isActive = activeSpeech[name] || false;
      
      return (
        <div 
          key={name}
          className={`agent-node ${isActive ? 'active' : ''}`}
          style={{ left: `${x}%`, top: `${y}%` }}
        >
          <div className="agent-avatar">
            <Icon size={24} strokeWidth={1.5} />
            <div className="waveform">
              <div className="wave-bar"></div>
              <div className="wave-bar"></div>
              <div className="wave-bar"></div>
              <div className="wave-bar"></div>
              <div className="wave-bar"></div>
            </div>
          </div>
          <div className="agent-name">{name}</div>
        </div>
      );
    });
  };

  const renderTraceLines = () => {
    return Object.entries(AGENT_CONFIG).map(([name, conf]) => {
      const radiusPct = conf.orbit === 'inner' ? 22.5 : 42.5; 
      const theta = (conf.angle - 90) * (Math.PI / 180);
      const x = 50 + radiusPct * Math.cos(theta);
      const y = 50 + radiusPct * Math.sin(theta);
      const isActive = activeSpeech[name] || false;

      return (
        <line 
          key={`line-${name}`}
          x1="50%" y1="50%" x2={`${x}%`} y2={`${y}%`}
          className={`trace-line ${isActive ? 'active' : ''}`}
        />
      );
    });
  };

  return (
    <div className="war-room">
      
      {/* Header Overlays */}
      <div className="header-overlay">
        <div className="brand">
          <div className="brand-title">ELEPHANT</div>
          <div className="brand-subtitle">Operating System v2.0</div>
        </div>
        <div className="status-badge">
          <div style={{width:8, height:8, borderRadius:'50%', background:'var(--current-accent)', boxShadow:'0 0 10px var(--current-glow)'}}></div>
          {theme === 'operational' ? 'BLACK OP PROTOCOL ENGAGED' : 'STRATEGIC OVERWATCH ACTIVE'}
        </div>
      </div>

      {/* The Arena (Orbital View) */}
      <div className="arena">
        
        {/* Core Elements */}
        <div className="core-container">
          <div className={`core-sphere ${activeSpeech['orchestrator'] ? 'pulsing' : ''}`}>
            <Brain size={48} color={theme==='operational' ? '#220000' : '#002244'} />
            <div className="core-ring"></div>
          </div>
          <div className="core-label">THE CORE</div>
        </div>

        {/* Orbit Rings */}
        <div className="orbit-ring inner"></div>
        <div className="orbit-ring outer"></div>

        {/* Trace Lines (SVG) */}
        <svg className="traces" preserveAspectRatio="none">
          {renderTraceLines()}
        </svg>

        {/* Agent Nodes */}
        {renderAgentNodes()}

      </div>

      {/* Bottom Control Panels */}
      
      {/* Left: Input Console */}
      <div className="bottom-panel command-console">
        <div className="panel-header">
          <Terminal size={14} /> 
          <span>Directives (Mösyö Override)</span>
        </div>
        <div className="console-body">
          <textarea 
            className="command-input"
            placeholder="Awaiting orders..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleExecute(); }
            }}
          />
        </div>
        <div className="execute-bar">
          <button className="btn-eng" onClick={handleExecute}>Engage Directive</button>
        </div>
      </div>

      {/* Right: Intel Feed */}
      <div className="bottom-panel intel-feed">
        <div className="panel-header">
          <Activity size={14} />
          <span>Live Intel Stream</span>
        </div>
        <div className="feed-body">
          {logs.map((log) => (
            <div key={log.id} className={`feed-item ${log.type.includes('error') ? 'error' : ''}`}>
              <span className="feed-time">[{log.time}]</span>
              <span className="feed-src">[{log.source.toUpperCase()}]</span>
              <span className="feed-msg">{log.msg}</span>
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>

    </div>
  );
}
