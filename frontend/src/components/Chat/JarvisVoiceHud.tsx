import { useState, useEffect } from 'react';
import {
  Mic,
  Volume2,
  VolumeX,
  Cpu,
  Maximize2,
  Minimize2,
  Sparkles,
  Terminal,
  Zap,
  Crown,
  Activity,
  Pin,
  PictureInPicture2,
  Play,
  Square,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { useTtsStore } from '../../lib/tts';

export type JarvisHudStatus = 'idle' | 'recording' | 'transcribing' | 'thinking' | 'tool' | 'speaking';

declare global {
  interface Window {
    jarvisElectron?: {
      isElectron: boolean;
      toggleAlwaysOnTop: () => Promise<boolean>;
      toggleMiniMode: () => Promise<boolean>;
      minimizeWindow: () => void;
      maximizeWindow: () => void;
      closeWindow: () => void;
    };
  }
}

const BRAIN_PRESETS = [
  {
    id: 'gemini-3.5-flash',
    label: 'Gemini 3.5 Flash',
    badge: '⚡ 1.5s Ultra-Rápido',
    desc: 'API Google Direta — Resposta instantânea para voz',
    icon: Zap,
  },
  {
    id: 'gemini-3.8-flash',
    label: 'Gemini 3.8 Flash',
    badge: '🚀 Google 3.8',
    desc: 'API Google Direta — Alta precisão e velocidade',
    icon: Sparkles,
  },
  {
    id: 'gemini-4-argon-low',
    label: 'Argon Maestro (Ágil)',
    badge: '👑 Argon Low',
    desc: 'Maestro Antigravity — Conectado ao seu ambiente e Obsidian',
    icon: Crown,
  },
  {
    id: 'gemini-4-argon-medium',
    label: 'Argon Maestro (Sênior)',
    badge: '🧠 Argon Medium',
    desc: 'Maestro Antigravity — Raciocínio profundo e arquitetura',
    icon: Crown,
  },
  {
    id: 'qwen3.5:4b',
    label: 'Qwen 3.5 (Local)',
    badge: '🖥️ RTX 3060',
    desc: 'Ollama Local Offline na sua placa de vídeo',
    icon: Cpu,
  },
];

const QUICK_COMMANDS = [
  {
    label: '⚡ Status Maestro & Hoje',
    prompt:
      'Jarvis, faça um briefing rápido e direto em português sobre como você pode me ajudar hoje no projeto Fluire e nos meus estudos de ADS.',
  },
  {
    label: '🏋️ Arquitetura Fluire',
    prompt:
      'Jarvis, resuma em tópicos curtos os pontos principais da nossa arquitetura do Fluire (React + Vite no Frontend, Flask + JWT no Backend e PostgreSQL no Supabase).',
  },
  {
    label: '🎯 Revisão de Código / Ideia',
    prompt:
      'Jarvis, estou pronto para revisar uma funcionalidade ou planejar uma nova rota. Me pergunte qual módulo vamos trabalhar agora.',
  },
];

export function JarvisVoiceHud() {
  const [expanded, setExpanded] = useState(true);
  const [micState, setMicState] = useState<'idle' | 'recording' | 'transcribing'>('idle');
  const [alwaysOnTop, setAlwaysOnTop] = useState(false);
  const [miniMode, setMiniMode] = useState(false);

  const streamState = useAppStore((s) => s.streamState);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const setSelectedModel = useAppStore((s) => s.setSelectedModel);
  const messages = useAppStore((s) => s.messages);
  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);

  const ttsState = useTtsStore((s) => s.state);
  const stopTts = useTtsStore((s) => s.stop);
  const speakTts = useTtsStore((s) => s.speak);

  // Switch default model from slow Ollama to fast Google Gemini 3.5 Flash once
  useEffect(() => {
    const migrated = localStorage.getItem('jarvis-google-brain-v2');
    if (!migrated || !selectedModel || selectedModel === 'qwen3.5:4b') {
      setSelectedModel('gemini-3.5-flash');
      localStorage.setItem('jarvis-google-brain-v2', 'true');
    }
  }, [selectedModel, setSelectedModel]);

  // Sync microphone state broadcasted from InputArea
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<'idle' | 'recording' | 'transcribing'>).detail;
      if (detail) setMicState(detail);
    };
    window.addEventListener('jarvis-mic-state', handler);
    return () => window.removeEventListener('jarvis-mic-state', handler);
  }, []);

  const triggerMicToggle = () => {
    if (ttsState === 'speaking') {
      stopTts();
    }
    window.dispatchEvent(new CustomEvent('jarvis-toggle-mic'));
  };

  const triggerQuickPrompt = (prompt: string) => {
    if (ttsState === 'speaking') {
      stopTts();
    }
    window.dispatchEvent(new CustomEvent('jarvis-send-prompt', { detail: prompt }));
  };

  const triggerVoiceGreeting = () => {
    if (ttsState === 'speaking') {
      stopTts();
      return;
    }
    void speakTts(
      `jarvis-greeting-${Date.now()}`,
      'Olá Senhor Caio. Todos os sistemas do seu J.A.R.V.I.S. e do Maestro estão conectados à sua chave da Google com resposta instantânea. Como posso ajudá-lo agora?',
    );
  };

  const activeTool =
    streamState.activeToolCalls && streamState.activeToolCalls.length > 0
      ? streamState.activeToolCalls[streamState.activeToolCalls.length - 1]
      : null;

  let hudStatus: JarvisHudStatus = 'idle';
  if (micState === 'recording') hudStatus = 'recording';
  else if (micState === 'transcribing') hudStatus = 'transcribing';
  else if (streamState.isStreaming && activeTool?.status === 'running') hudStatus = 'tool';
  else if (streamState.isStreaming) hudStatus = 'thinking';
  else if (ttsState === 'speaking' || ttsState === 'loading') hudStatus = 'speaking';

  const statusConfig: Record<
    JarvisHudStatus,
    { label: string; sublabel: string; color: string; glow: string; ringSpeed: string }
  > = {
    idle: {
      label: 'J.A.R.V.I.S. • MAESTRO HUB ONLINE',
      sublabel: 'Clique no Reator Arc para falar por voz ou escolha uma ação com o mouse',
      color: '#00e5ff',
      glow: 'rgba(0, 229, 255, 0.38)',
      ringSpeed: '14s',
    },
    recording: {
      label: 'OUVINDO SUA VOZ AO VIVO...',
      sublabel: 'Fale naturalmente • Clique no Reator Arc para concluir e enviar',
      color: '#ff3d00',
      glow: 'rgba(255, 61, 0, 0.6)',
      ringSpeed: '2.2s',
    },
    transcribing: {
      label: 'TRANSCREVENDO ÁUDIO (FASTER-WHISPER)...',
      sublabel: 'Convertendo sua voz em comando para o Maestro',
      color: '#ffab00',
      glow: 'rgba(255, 171, 0, 0.5)',
      ringSpeed: '1.8s',
    },
    thinking: {
      label: `PROCESSANDO COM ${(selectedModel || 'GEMINI').toUpperCase()}...`,
      sublabel: streamState.phase || 'Recebendo stream em tempo real da Google Cloud / Argon',
      color: '#00b0ff',
      glow: 'rgba(0, 176, 255, 0.55)',
      ringSpeed: '2.4s',
    },
    tool: {
      label: `EXECUTANDO FERRAMENTA: ${activeTool?.tool?.toUpperCase() || 'AGENTE'}`,
      sublabel: activeTool?.arguments ? `Parâmetros: ${activeTool.arguments.slice(0, 80)}` : 'Orquestrando ação no sistema...',
      color: '#00e676',
      glow: 'rgba(0, 230, 118, 0.55)',
      ringSpeed: '1.6s',
    },
    speaking: {
      label: 'J.A.R.V.I.S. FALANDO COM VOCÊ',
      sublabel: 'Voz Neural PT-BR (AntonioNeural) • Clique no Orbe para interromper',
      color: '#00e5ff',
      glow: 'rgba(0, 229, 255, 0.75)',
      ringSpeed: '1.4s',
    },
  };

  const current = statusConfig[hudStatus];
  const lastAssistantMsg = [...messages].reverse().find((m) => m.role === 'assistant');
  const liveSubtitle = streamState.isStreaming
    ? streamState.content
    : lastAssistantMsg?.content ||
      'Sistemas J.A.R.V.I.S. e Maestro conectados à API Google (Gemini Flash & Argon). Clique no núcleo azul para falar comigo ou use os botões rápidos com o mouse!';

  const isElectron = Boolean(window.jarvisElectron?.isElectron);

  return (
    <div
      className="mx-4 mt-2 mb-1 rounded-2xl transition-all duration-300 select-none overflow-hidden shrink-0"
      style={{
        background: 'linear-gradient(135deg, rgba(6, 15, 28, 0.97) 0%, rgba(10, 24, 44, 0.94) 100%)',
        border: `1px solid ${current.color}66`,
        boxShadow: `0 0 28px -4px ${current.glow}`,
      }}
    >
      <style>{`
        @keyframes jarvis-spin-cw {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes jarvis-spin-ccw {
          from { transform: rotate(360deg); }
          to { transform: rotate(0deg); }
        }
        @keyframes jarvis-wave {
          0%, 100% { transform: scaleY(0.3); opacity: 0.5; }
          50% { transform: scaleY(1.25); opacity: 1; }
        }
      `}</style>

      {/* Top Header Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2.5 gap-3">
        {/* Left: Interactive Arc Reactor Core + Status */}
        <div className="flex items-center gap-3.5 min-w-0">
          <button
            type="button"
            onClick={triggerMicToggle}
            title={hudStatus === 'recording' ? 'Clique para parar e enviar sua fala' : 'Clique para falar com o J.A.R.V.I.S.'}
            className="relative flex items-center justify-center w-12 h-12 rounded-full cursor-pointer transition-transform hover:scale-105 active:scale-95 shrink-0"
            style={{
              background: 'radial-gradient(circle, rgba(0,229,255,0.22) 0%, rgba(0,0,0,0.65) 80%)',
              boxShadow: `0 0 18px ${current.glow}`,
            }}
          >
            <svg width="48" height="48" viewBox="0 0 100 100" className="absolute inset-0">
              <circle
                cx="50"
                cy="50"
                r="44"
                fill="none"
                stroke={current.color}
                strokeWidth="3"
                strokeDasharray="24 10 12 10"
                style={{
                  transformOrigin: '50% 50%',
                  animation: `jarvis-spin-cw ${current.ringSpeed} linear infinite`,
                }}
              />
              <circle
                cx="50"
                cy="50"
                r="34"
                fill="none"
                stroke={current.color}
                strokeWidth="2"
                strokeOpacity="0.75"
                strokeDasharray="16 14"
                style={{
                  transformOrigin: '50% 50%',
                  animation: `jarvis-spin-ccw ${current.ringSpeed} linear infinite`,
                }}
              />
              <circle
                cx="50"
                cy="50"
                r={hudStatus === 'speaking' || hudStatus === 'recording' ? '20' : '16'}
                fill={current.color}
                fillOpacity={hudStatus === 'idle' ? '0.25' : '0.45'}
              />
            </svg>
            <Mic
              size={18}
              style={{
                color: '#ffffff',
                filter: `drop-shadow(0 0 6px ${current.color})`,
                zIndex: 2,
              }}
            />
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className="text-xs font-bold tracking-wider uppercase truncate"
                style={{ color: current.color, textShadow: `0 0 10px ${current.glow}` }}
              >
                {current.label}
              </span>
              {(hudStatus === 'speaking' || hudStatus === 'recording' || hudStatus === 'thinking') && (
                <div className="flex items-center gap-0.5 h-3.5 px-1">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <span
                      key={i}
                      className="w-0.5 h-3 rounded-full"
                      style={{
                        backgroundColor: current.color,
                        animation: `jarvis-wave 0.65s ease-in-out ${i * 0.11}s infinite`,
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
            <div className="text-[11px] truncate mt-0.5" style={{ color: 'rgba(200, 232, 255, 0.78)' }}>
              {current.sublabel}
            </div>
          </div>
        </div>

        {/* Right: Interactive Mouse Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Test Voice Button */}
          <button
            type="button"
            onClick={triggerVoiceGreeting}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium cursor-pointer transition-all hover:scale-105"
            style={{
              background: ttsState === 'speaking' ? 'rgba(255, 61, 0, 0.2)' : 'rgba(0, 229, 255, 0.12)',
              border: `1px solid ${ttsState === 'speaking' ? '#ff3d00' : 'rgba(0, 229, 255, 0.35)'}`,
              color: ttsState === 'speaking' ? '#ff6e40' : '#a8e6ff',
            }}
            title={ttsState === 'speaking' ? 'Parar fala do J.A.R.V.I.S.' : 'Ouvir saudação de voz do J.A.R.V.I.S.'}
          >
            {ttsState === 'speaking' ? <Square size={11} /> : <Play size={11} />}
            <span>{ttsState === 'speaking' ? 'Parar Fala' : 'Testar Voz'}</span>
          </button>

          {/* Voice Autoplay Toggle */}
          <button
            type="button"
            onClick={() => {
              if (ttsState === 'speaking') stopTts();
              const next = !(settings.voiceOutputEnabled && settings.voiceAutoplay);
              updateSettings({ voiceOutputEnabled: next, voiceAutoplay: next, speechEnabled: true });
            }}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium cursor-pointer transition-colors"
            style={{
              background:
                settings.voiceOutputEnabled && settings.voiceAutoplay
                  ? 'rgba(0, 229, 255, 0.2)'
                  : 'rgba(255, 255, 255, 0.06)',
              border: `1px solid ${
                settings.voiceOutputEnabled && settings.voiceAutoplay
                  ? 'rgba(0, 229, 255, 0.5)'
                  : 'rgba(255, 255, 255, 0.15)'
              }`,
              color: settings.voiceOutputEnabled && settings.voiceAutoplay ? '#00e5ff' : 'rgba(255,255,255,0.5)',
            }}
            title="Ativar/Desativar resposta falada automática do J.A.R.V.I.S."
          >
            {settings.voiceOutputEnabled && settings.voiceAutoplay ? <Volume2 size={13} /> : <VolumeX size={13} />}
            <span className="hidden md:inline">Voz Auto</span>
          </button>

          {/* Electron Always-On-Top & Mini-HUD Controls */}
          {isElectron && (
            <>
              <button
                type="button"
                onClick={async () => {
                  const pinned = await window.jarvisElectron?.toggleAlwaysOnTop();
                  setAlwaysOnTop(Boolean(pinned));
                }}
                className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium cursor-pointer transition-colors"
                style={{
                  background: alwaysOnTop ? 'rgba(0, 230, 118, 0.2)' : 'rgba(255, 255, 255, 0.06)',
                  border: `1px solid ${alwaysOnTop ? '#00e676' : 'rgba(255, 255, 255, 0.15)'}`,
                  color: alwaysOnTop ? '#00e676' : '#a8e6ff',
                }}
                title="Fixar J.A.R.V.I.S. sempre no topo das outras janelas do Windows"
              >
                <Pin size={12} />
                <span className="hidden lg:inline">Fixar Topo</span>
              </button>

              <button
                type="button"
                onClick={async () => {
                  const isMini = await window.jarvisElectron?.toggleMiniMode();
                  setMiniMode(Boolean(isMini));
                }}
                className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium cursor-pointer transition-colors"
                style={{
                  background: miniMode ? 'rgba(0, 229, 255, 0.22)' : 'rgba(255, 255, 255, 0.06)',
                  border: `1px solid ${miniMode ? '#00e5ff' : 'rgba(255, 255, 255, 0.15)'}`,
                  color: miniMode ? '#00e5ff' : '#a8e6ff',
                }}
                title="Alternar entre Janela Compacta Flutuante e Console Completo"
              >
                <PictureInPicture2 size={12} />
                <span className="hidden lg:inline">{miniMode ? 'Janela Normal' : 'Mini HUD'}</span>
              </button>
            </>
          )}

          {/* Expand / Collapse HUB */}
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 rounded-lg cursor-pointer transition-colors"
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              color: '#a8e6ff',
            }}
            title={expanded ? 'Recolher Painel HUB' : 'Expandir Painel HUB Interativo'}
          >
            {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Interactive Brain Switcher Bar (Always Accessible with Mouse) */}
      <div
        className="px-4 py-2 flex flex-wrap items-center gap-1.5"
        style={{
          borderTop: '1px solid rgba(0, 229, 255, 0.14)',
          background: 'rgba(0, 10, 22, 0.55)',
        }}
      >
        <span className="text-[10px] font-mono uppercase tracking-wider mr-1" style={{ color: '#70a8cc' }}>
          Cérebro Ativo:
        </span>
        {BRAIN_PRESETS.map((brain) => {
          const isSelected = selectedModel === brain.id;
          return (
            <button
              key={brain.id}
              type="button"
              onClick={() => setSelectedModel(brain.id)}
              title={brain.desc}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium cursor-pointer transition-all"
              style={{
                background: isSelected
                  ? 'linear-gradient(135deg, rgba(0, 229, 255, 0.25), rgba(0, 140, 255, 0.2))'
                  : 'rgba(255, 255, 255, 0.04)',
                border: `1px solid ${isSelected ? '#00e5ff' : 'rgba(255, 255, 255, 0.1)'}`,
                color: isSelected ? '#ffffff' : 'rgba(180, 215, 240, 0.75)',
                boxShadow: isSelected ? '0 0 12px rgba(0, 229, 255, 0.25)' : 'none',
              }}
            >
              <span>{brain.badge}</span>
              <span className="hidden sm:inline opacity-90">({brain.label})</span>
            </button>
          );
        })}
      </div>

      {/* Expanded Interactive HUB Console */}
      {expanded && (
        <div
          className="px-5 py-4 flex flex-col md:flex-row items-center gap-5"
          style={{
            borderTop: '1px solid rgba(0, 229, 255, 0.2)',
            background: 'radial-gradient(circle at 20% 50%, rgba(0, 229, 255, 0.14), rgba(4, 10, 20, 0.96) 72%)',
          }}
        >
          {/* Giant Interactive Arc Reactor Orb */}
          <div className="flex flex-col items-center shrink-0">
            <button
              type="button"
              onClick={triggerMicToggle}
              className="relative flex items-center justify-center w-32 h-32 rounded-full cursor-pointer transition-transform hover:scale-105 active:scale-95"
              style={{
                boxShadow: `0 0 42px ${current.glow}`,
              }}
            >
              <svg width="128" height="128" viewBox="0 0 200 200" className="absolute inset-0">
                <circle
                  cx="100"
                  cy="100"
                  r="90"
                  fill="none"
                  stroke={current.color}
                  strokeWidth="4"
                  strokeDasharray="40 15 20 15"
                  style={{
                    transformOrigin: '50% 50%',
                    animation: `jarvis-spin-cw ${current.ringSpeed} linear infinite`,
                  }}
                />
                <circle
                  cx="100"
                  cy="100"
                  r="74"
                  fill="none"
                  stroke={current.color}
                  strokeWidth="2.5"
                  strokeOpacity="0.8"
                  strokeDasharray="25 18"
                  style={{
                    transformOrigin: '50% 50%',
                    animation: `jarvis-spin-ccw ${current.ringSpeed} linear infinite`,
                  }}
                />
                <circle
                  cx="100"
                  cy="100"
                  r="56"
                  fill="none"
                  stroke={current.color}
                  strokeWidth="1.5"
                  strokeOpacity="0.5"
                  strokeDasharray="8 8"
                  style={{
                    transformOrigin: '50% 50%',
                    animation: `jarvis-spin-cw 8s linear infinite`,
                  }}
                />
                <circle
                  cx="100"
                  cy="100"
                  r={hudStatus === 'speaking' || hudStatus === 'recording' ? '42' : '34'}
                  fill={current.color}
                  fillOpacity="0.35"
                />
              </svg>
              <div className="z-10 flex flex-col items-center gap-1">
                <Mic size={26} color="#fff" />
                <span className="text-[10px] font-mono font-bold tracking-widest uppercase" style={{ color: '#fff' }}>
                  {hudStatus === 'recording' ? 'ENVIAR VOZ' : 'CLIQUE & FALE'}
                </span>
              </div>
            </button>
          </div>

          {/* Right: Live Subtitle + Mouse Quick-Command Buttons */}
          <div className="flex-1 min-w-0 w-full">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <div className="flex items-center gap-2">
                <Terminal size={13} style={{ color: current.color }} />
                <span className="text-[11px] font-mono uppercase tracking-wider" style={{ color: current.color }}>
                  Visor Holográfico de Resposta & Voz
                </span>
              </div>
              <span className="text-[10px] font-mono flex items-center gap-1" style={{ color: '#68a8d8' }}>
                <Activity size={11} style={{ color: '#00e676' }} />
                Google API + Edge Neural PT-BR
              </span>
            </div>

            <div
              className="rounded-xl p-3 font-mono text-xs leading-relaxed max-h-28 overflow-y-auto"
              style={{
                background: 'rgba(0, 0, 0, 0.58)',
                border: '1px solid rgba(0, 229, 255, 0.25)',
                color: '#e4f5ff',
              }}
            >
              {liveSubtitle.slice(0, 520)}
              {liveSubtitle.length > 520 ? '...' : ''}
            </div>

            {/* Quick-Command Mouse Buttons */}
            <div className="flex flex-wrap items-center gap-2 mt-2.5">
              {QUICK_COMMANDS.map((cmd) => (
                <button
                  key={cmd.label}
                  type="button"
                  onClick={() => triggerQuickPrompt(cmd.prompt)}
                  disabled={streamState.isStreaming}
                  className="px-3 py-1.5 rounded-lg text-[11px] font-medium cursor-pointer transition-all hover:scale-[1.02] active:scale-95 disabled:opacity-50"
                  style={{
                    background: 'rgba(0, 229, 255, 0.1)',
                    border: '1px solid rgba(0, 229, 255, 0.28)',
                    color: '#bceaff',
                  }}
                >
                  {cmd.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
