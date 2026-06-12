interface EyeLogoProps {
  size?: number;
  className?: string;
  animated?: boolean;
}

export default function EyeLogo({ size = 40, className = '', animated = true }: EyeLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Citévision"
    >
      <defs>
        <linearGradient id="eyeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#00D4FF" />
          <stop offset="100%" stopColor="#0099CC" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Outer ring */}
      <circle
        cx="24"
        cy="24"
        r="20"
        stroke="url(#eyeGrad)"
        strokeWidth="1.5"
        fill="none"
        opacity="0.6"
        className={animated ? 'origin-center animate-pulse-slow' : ''}
      />

      {/* Eye shape */}
      <path
        d="M6 24 C6 24, 14 10, 24 10 C34 10, 42 24, 42 24 C42 24, 34 38, 24 38 C14 38, 6 24, 6 24 Z"
        stroke="url(#eyeGrad)"
        strokeWidth="1.5"
        fill="rgba(0, 212, 255, 0.05)"
        filter="url(#glow)"
      />

      {/* Iris */}
      <circle cx="24" cy="24" r="8" stroke="#00D4FF" strokeWidth="1" fill="rgba(0, 212, 255, 0.15)">
        {animated && (
          <animate attributeName="r" values="8;8.5;8" dur="3s" repeatCount="indefinite" />
        )}
      </circle>

      {/* Pupil */}
      <circle cx="24" cy="24" r="3.5" fill="#00D4FF">
        {animated && (
          <>
            <animate attributeName="r" values="3.5;2.5;3.5" dur="4s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="1;0.7;1" dur="4s" repeatCount="indefinite" />
          </>
        )}
      </circle>

      {/* Scan line */}
      {animated && (
        <line x1="10" y1="24" x2="38" y2="24" stroke="#00D4FF" strokeWidth="0.5" opacity="0.4">
          <animate attributeName="y1" values="14;34;14" dur="2.5s" repeatCount="indefinite" />
          <animate attributeName="y2" values="14;34;14" dur="2.5s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0;0.6;0" dur="2.5s" repeatCount="indefinite" />
        </line>
      )}

      {/* Corner accents */}
      <path d="M4 12 L4 4 L12 4" stroke="#00D4FF" strokeWidth="1" fill="none" opacity="0.5" />
      <path d="M44 12 L44 4 L36 4" stroke="#00D4FF" strokeWidth="1" fill="none" opacity="0.5" />
      <path d="M4 36 L4 44 L12 44" stroke="#00D4FF" strokeWidth="1" fill="none" opacity="0.5" />
      <path d="M44 36 L44 44 L36 44" stroke="#00D4FF" strokeWidth="1" fill="none" opacity="0.5" />
    </svg>
  );
}
