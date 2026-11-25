"use client";
import {useEffect,useState} from "react";
import {ArrowRight,DoorOpen,Pause,Play,RotateCcw} from "lucide-react";
import {Button,Card} from "./ui";
import type {AcademicSession} from "./teaching-planner";
const DAYS=["Lunes","Martes","Miércoles","Jueves","Viernes"];
const clock=(m:number)=>String(Math.floor(m/60)).padStart(2,"0")+":"+String(m%60).padStart(2,"0");
export function RoomFlow({rows,rooms,colors,generated}:{rows:AcademicSession[];rooms:string[];colors:Map<string,string>;generated:boolean}){
 const [frame,setFrame]=useState(0),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(900);
 useEffect(()=>{if(!playing)return;const timer=setInterval(()=>setFrame(n=>{if(n>=129){setPlaying(false);return 129;}return n+1;}),speed);return()=>clearInterval(timer);},[playing,speed]);
 useEffect(()=>{setPlaying(false);setFrame(0);},[rows]);
 const day=Math.floor(frame/26),minute=420+(frame%26)*30;
 const lunch=minute>=780&&minute<840;
 const active=rows.filter(s=>s.day===day&&s.start<=minute&&minute<s.end);
 const occupied=new Set(active.map(s=>s.room));
 return <Card id="flujo-aulas" className="product-card">
  <div className="planning-heading"><div><h2 className="text-xl font-bold flex items-center gap-2"><DoorOpen size={22}/> Flujo de las aulas</h2><p className="muted mt-1">Recorre la semana para ver qué se imparte, quién ocupa cada aula y cuál es la siguiente actividad.</p></div><span className="planning-badge">{generated?"Horario generado":"Vista del horario inicial"}</span></div>
  <div className="flow-controls"><label className="label">Día de simulación<select className="field" aria-label="Día de simulación" value={day} onChange={e=>{setPlaying(false);setFrame(Number(e.target.value)*26+frame%26);}}>{DAYS.map((d,i)=><option key={d} value={i}>{d}</option>)}</select></label><div className="flow-clock"><span>{DAYS[day]}</span><strong>{clock(minute)}</strong><small>{lunch?"Receso de almuerzo":minute<780?"Jornada de mañana":"Jornada de tarde"}</small></div><div className="flow-count"><strong>{occupied.size} / {rooms.length}</strong><span>aulas ocupadas</span></div><Button type="button" variant="outline" onClick={()=>{setPlaying(false);setFrame(0);}}><RotateCcw size={16}/> Reiniciar</Button><Button type="button" disabled={!rows.length} onClick={()=>{if(frame===129)setFrame(0);setPlaying(p=>!p);}}>{playing?<Pause size={16}/>:<Play size={16}/>} {playing?"Pausar simulación":"Reproducir simulación"}</Button></div>
  <div className="flow-slider"><label htmlFor="room-time">Hora de simulación · pasos de 30 minutos</label><input id="room-time" aria-label="Hora de simulación" type="range" min={0} max={25} value={frame%26} onChange={e=>{setPlaying(false);setFrame(day*26+Number(e.target.value));}}/><div><span>07:00</span><span>13:00 · Receso · 14:00</span><span>19:30</span></div></div>
  <div className="room-map">{rooms.map(room=>{
   const now=active.filter(s=>s.room===room);
   const next=rows.filter(s=>s.room===room&&(s.day>day||s.day===day&&s.start>minute)).sort((a,b)=>a.day-b.day||a.start-b.start)[0];
   return <article className={"room-node "+(now.length>1?"room-conflict":now.length?"room-occupied":"room-free")} key={room}>
    <header><span className="room-door"><DoorOpen size={19}/> Aula {room}</span><span className="room-status">{now.length>1?"Cruce detectado":now.length?"Ocupada":lunch?"Receso":"Libre"}</span></header>
    <div className="room-current">{now.length?now.map(s=><div className="room-lesson" key={s.id} style={{borderColor:colors.get(s.teacher)??"#593dc5"}}><small>{clock(s.start)}–{clock(s.end)} · {s.kind==="tutoring"?"Tutoría":"Clase"}</small><strong>{s.course}</strong><span><i style={{background:colors.get(s.teacher)??"#593dc5"}}/>{s.teacher}</span><span>{s.level} · Paralelo {s.section}</span><span>Termina en {s.end-minute} min</span></div>):<div className="room-empty"><DoorOpen size={25}/><strong>{lunch?"Pausa de almuerzo":"Aula disponible"}</strong><span>{lunch?"13:00–14:00":"Sin actividad en este momento"}</span></div>}</div>
    <footer><ArrowRight size={14}/><div><small>Siguiente actividad</small>{next?<><strong>{DAYS[next.day]??"Otro día"} {clock(next.start)} · {next.course}</strong><span>{next.teacher} · {next.level} {next.section}</span></>:<span>Sin más actividades esta semana</span>}</div></footer>
   </article>;
  })}</div>
  <div className="flow-footer"><p className="muted">Se simula la ocupación de todas las aulas, sin aplicar los filtros del calendario. Las tarjetas muestran los cruces si existen. No se estima afluencia de estudiantes sin matrículas.</p><label className="label">Velocidad<select className="field" aria-label="Velocidad de simulación" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1500}>Lenta</option><option value={900}>Normal</option><option value={350}>Rápida</option></select></label></div>
 </Card>;
}
