import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type Point = { month: string; net: string; approximate: number };
export default function SalesChart({ chart, currency, format }: { chart: Point[]; currency: string; format: (value: string) => string }) {
  return <ResponsiveContainer width="100%" height={280} initialDimension={{ width: 650, height: 280 }}><LineChart data={chart} margin={{ top: 20, right: 25, bottom: 10, left: 15 }}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="month"/><YAxis width={75} tickFormatter={(value: number) => new Intl.NumberFormat('fr-FR', { notation: 'compact' }).format(value)}/><Tooltip content={({ active, payload }) => active && payload?.length ? <div className="card dashboard-tooltip">{(payload[0].payload as Point).month}<br/>{format((payload[0].payload as Point).net)} {currency}</div> : null}/><Line dataKey="approximate" name="Net facturé TTC" stroke="#6D5DF5" strokeWidth={3} isAnimationActive={false}/></LineChart></ResponsiveContainer>;
}
