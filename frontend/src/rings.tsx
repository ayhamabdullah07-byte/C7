import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { tokens } from './theme';

export function CalorieRing({
  consumed,
  target,
  size = 220,
  stroke = 14,
  label,
  sub,
}: {
  consumed: number;
  target: number;
  size?: number;
  stroke?: number;
  label?: string;
  sub?: string;
}) {
  const radius = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = target > 0 ? Math.min(1, Math.max(0, consumed / target)) : 0;
  const dash = circumference * pct;
  const remaining = Math.max(0, Math.round(target - consumed));
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle
          cx={cx}
          cy={cy}
          r={radius}
          stroke={tokens.bg3}
          strokeWidth={stroke}
          fill="none"
        />
        <Circle
          cx={cx}
          cy={cy}
          r={radius}
          stroke={tokens.brand}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={`${dash} ${circumference - dash}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
        />
      </Svg>
      <View style={StyleSheet.absoluteFill as any}>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={s.big} testID="calorie-ring-remaining">
            {remaining}
          </Text>
          <Text style={s.sub}>{label || 'kcal left'}</Text>
          <Text style={s.dim}>{sub || `${Math.round(consumed)} / ${target}`}</Text>
        </View>
      </View>
    </View>
  );
}

export function MacroBar({
  name,
  value,
  target,
  color,
  unit = 'g',
}: {
  name: string;
  value: number;
  target: number;
  color: string;
  unit?: string;
}) {
  const pct = target > 0 ? Math.min(1, value / target) : 0;
  return (
    <View style={s.macroWrap}>
      <View style={s.macroHeader}>
        <Text style={s.macroName}>{name}</Text>
        <Text style={s.macroVal}>
          {Math.round(value)}<Text style={s.macroTarget}> / {Math.round(target)}{unit}</Text>
        </Text>
      </View>
      <View style={s.track}>
        <View style={[s.fill, { width: `${pct * 100}%`, backgroundColor: color }]} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  big: { color: tokens.text, fontSize: 44, fontWeight: '800', letterSpacing: -1 },
  sub: { color: tokens.brand, fontSize: 13, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', marginTop: 2 },
  dim: { color: tokens.textMute, fontSize: 12, marginTop: 4 },
  macroWrap: { marginBottom: tokens.md },
  macroHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  macroName: { color: tokens.textDim, fontSize: 13, fontWeight: '600' },
  macroVal: { color: tokens.text, fontSize: 13, fontWeight: '700' },
  macroTarget: { color: tokens.textMute, fontWeight: '500' },
  track: { height: 6, backgroundColor: tokens.bg3, borderRadius: 999, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 999 },
});
