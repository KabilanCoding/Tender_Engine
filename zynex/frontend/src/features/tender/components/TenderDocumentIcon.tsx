import React from 'react';

interface TenderDocumentIconProps {
  className?: string;
  size?: number | string;
}

export const TenderDocumentIcon: React.FC<TenderDocumentIconProps> = ({
  className = "w-20 h-20",
}) => {
  return (
    <div className={`relative inline-flex items-center justify-center flex-shrink-0 ${className}`}>
      {/* Background Soft Radial Glow */}
      <div className="absolute inset-0 bg-gradient-to-tr from-indigo-500/25 via-violet-500/20 to-emerald-400/20 rounded-3xl blur-xl transform scale-125 -z-10" />

      <svg
        viewBox="0 0 160 160"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full drop-shadow-xl transition-all duration-300 transform group-hover:scale-105"
      >
        <defs>
          {/* Main Card Gradient */}
          <linearGradient id="proDocGrad" x1="20" y1="20" x2="140" y2="140" gradientUnits="userSpaceOnUse">
            <stop stopColor="#1A59BD" />
            <stop offset="0.5" stopColor="#014BAA" />
            <stop offset="1" stopColor="#02316F" />
          </linearGradient>

          {/* Fold Corner Gradient */}
          <linearGradient id="proFoldGrad" x1="100" y1="20" x2="130" y2="50" gradientUnits="userSpaceOnUse">
            <stop stopColor="#A9C4F5" />
            <stop offset="1" stopColor="#1A59BD" />
          </linearGradient>

          {/* Accent Glass Shield Gradient */}
          <linearGradient id="proShieldGrad" x1="60" y1="70" x2="100" y2="130" gradientUnits="userSpaceOnUse">
            <stop stopColor="#10B981" />
            <stop offset="1" stopColor="#059669" />
          </linearGradient>

          {/* Gold Sparkle Badge */}
          <linearGradient id="proSparkleGrad" x1="110" y1="70" x2="140" y2="100" gradientUnits="userSpaceOnUse">
            <stop stopColor="#F59E0B" />
            <stop offset="1" stopColor="#D97706" />
          </linearGradient>

          {/* Subtle Inner Glow Filter */}
          <filter id="shadowFilter" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="8" stdDeviation="6" floodColor="#032553" floodOpacity="0.25" />
          </filter>
        </defs>

        {/* Back Document Sheet (Layered Offset Effect) */}
        <rect
          x="32"
          y="28"
          width="90"
          height="110"
          rx="12"
          fill="#02316F"
          fillOpacity="0.4"
          transform="rotate(-4 77 83)"
        />

        {/* Main Document Body */}
        <g filter="url(#shadowFilter)">
          <path
            d="M 36 24 C 36 17.37 41.37 12 48 12 L 98 12 L 128 42 L 128 132 C 128 138.63 122.63 144 116 144 L 48 144 C 41.37 144 36 138.63 36 132 Z"
            fill="url(#proDocGrad)"
            stroke="#8FB3F2"
            strokeWidth="2.5"
          />

          {/* Folded Top-Right Corner */}
          <path
            d="M 98 12 L 98 34 C 98 38.42 101.58 42 106 42 L 128 42 Z"
            fill="url(#proFoldGrad)"
            stroke="#8FB3F2"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        </g>

        {/* Document Header & Text Content Lines */}
        <g opacity="0.9">
          {/* Header Title Line */}
          <rect x="52" y="32" width="36" height="5" rx="2.5" fill="#F2F6FC" />
          
          {/* Structural Lines */}
          <rect x="52" y="46" width="60" height="3" rx="1.5" fill="#DCE6FA" opacity="0.7" />
          <rect x="52" y="56" width="52" height="3" rx="1.5" fill="#DCE6FA" opacity="0.7" />
          <rect x="52" y="66" width="44" height="3" rx="1.5" fill="#DCE6FA" opacity="0.7" />
        </g>

        {/* Upload Arrow / Analysis Symbol Badge (Center) */}
        <g transform="translate(48, 76)">
          {/* Outer Ring */}
          <circle cx="32" cy="32" r="28" fill="#032553" fillOpacity="0.6" stroke="#8FB3F2" strokeWidth="2" />
          
          {/* Upload Arrow Symbol */}
          <path
            d="M 32 44 L 32 20 M 32 20 L 23 29 M 32 20 L 41 29"
            stroke="#6EE7B7"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Checkmark Accent */}
          <circle cx="46" cy="46" r="8" fill="url(#proShieldGrad)" stroke="#ECFDF5" strokeWidth="1.5" />
          <path d="M 42 46 L 45 49 L 50 43" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </g>

        {/* Top Right Floating AI Sparkle Badge */}
        <g transform="translate(108, 68)">
          <circle cx="16" cy="16" r="14" fill="url(#proSparkleGrad)" stroke="#FEF3C7" strokeWidth="2" />
          {/* 4-point Sparkle Star */}
          <path
            d="M 16 7 C 16 11 12 16 8 16 C 12 16 16 21 16 25 C 16 21 20 16 24 16 C 20 16 16 11 16 7 Z"
            fill="#FFFFFF"
          />
        </g>
      </svg>
    </div>
  );
};

export default TenderDocumentIcon;

