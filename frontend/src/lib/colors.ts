export const tierColors: Record<string, { color: string; bg: string }> = {
  Elite:   { color: '#FFD600', bg: 'rgba(255,214,0,0.15)' },
  Strong:  { color: '#4da6ff', bg: 'rgba(77,166,255,0.15)' },
  Steady:  { color: '#00e87a', bg: 'rgba(0,232,122,0.12)' },
  Develop: { color: '#ff6b6b', bg: 'rgba(255,107,107,0.12)' },
};

export const tierColorsTwilio: Record<string, { color: string; bg: string }> = {
  Elite:   { color: '#B45309', bg: '#FEF3C7' },
  Strong:  { color: '#1D4ED8', bg: '#EFF6FF' },
  Steady:  { color: '#178742', bg: '#F0FDF4' },
  Develop: { color: '#DC2626', bg: '#FEF2F2' },
};

export const flagColors: Record<string, string> = {
  STANDING: '#94a3b8', PIPELINE: '#4da6ff',
  EXPANSION: '#00e87a', STRATEGIC: '#00e87a',
  HYGIENE: '#ff6b6b',
  ACTIVATE: '#ffaa44', 'NEW BUSINESS': '#ffaa44',
  RISK: '#ff4466', MOTION: '#b87cff', STRENGTH: '#00d4ff',
  NOTES: '#f59e0b',
};

export const flagColorsTwilio: Record<string, string> = {
  STANDING: '#6B7280', PIPELINE: '#006EFF',
  EXPANSION: '#178742', STRATEGIC: '#178742',
  HYGIENE: '#DC2626',
  ACTIVATE: '#D97706', 'NEW BUSINESS': '#D97706',
  RISK: '#DC2626', MOTION: '#7C3AED', STRENGTH: '#0891B2',
  NOTES: '#D97706',
};

export function tc(tier: string, currentTheme: string) {
  return currentTheme === 'twilio'
    ? (tierColorsTwilio[tier] ?? tierColorsTwilio.Steady)
    : (tierColors[tier] ?? tierColors.Steady);
}

export function fc(cat: string, currentTheme: string) {
  return currentTheme === 'twilio'
    ? (flagColorsTwilio[cat] ?? '#6B7280')
    : (flagColors[cat] ?? '#aaaaaa');
}
