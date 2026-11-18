import { useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { Button } from './components/ui/button';
export function ThemeToggle() {
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');
  document.documentElement.classList.toggle('dark', dark);
  return <Button variant="outline" aria-label={dark ? 'Activer le thème clair' : 'Activer le thème sombre'} onClick={() => setDark(value => { localStorage.setItem('theme', value ? 'light' : 'dark'); return !value; })}>{dark ? <Sun size={16}/> : <Moon size={16}/>}<span>Thème</span></Button>;
}
