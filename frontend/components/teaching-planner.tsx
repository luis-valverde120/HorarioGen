"use client";
import { useEffect, useState } from "react";
import { Plus, Save, Trash2, Users } from "lucide-react";
import { Button, Card } from "./ui";

export type AcademicSession = {id:number; kind?:"class"|"tutoring"; group_key?:string; program:string; major:string; level:string; section:string; course:string; teacher:string; room:string; day:number; start:number; end:number};
export type TeachingAssignment = {source_id:number; course:string; teacher:string; weekly_hours:number; block_hours:number; days:number[]};
const days = ["Lun", "Mar", "Mié", "Jue", "Vie"];
const keyOf = (s:AcademicSession) => s.group_key ?? JSON.stringify([s.program,s.major,s.level,s.section]);

export function TeachingPlanner({sessions, sessionDays, disabled, onSave, onDirtyChange}:{sessions:AcademicSession[]; sessionDays?:Record<string,number[]>; disabled:boolean; onSave:(items:TeachingAssignment[], useLoad:boolean)=>Promise<void>; onDirtyChange?:(dirty:boolean)=>void}) {
  const [items,setItems]=useState<TeachingAssignment[]>([]);
  const [group,setGroup]=useState("");
  const [useLoad,setUseLoad]=useState(true);
  const [notice,setNotice]=useState("");
  const [error,setError]=useState("");
  useEffect(()=>{
    const map=new Map<string,TeachingAssignment>();
    for(const row of sessions.filter(s=>s.kind!=="tutoring")) {
      const key=keyOf(row)+"|"+row.course.toLocaleLowerCase();
      const current=map.get(key);
      if(current) current.weekly_hours+=(row.end-row.start)/60;
      else map.set(key,{source_id:row.id,course:row.course,teacher:row.teacher,weekly_hours:(row.end-row.start)/60,block_hours:Math.min(4,(row.end-row.start)/60),days:sessionDays?.[row.id]??[0,1,2,3,4]});
    }
    setItems([...map.values()]);setGroup(sessions.find(s=>s.kind!=="tutoring")?keyOf(sessions.find(s=>s.kind!=="tutoring")!):"");setNotice("");setError("");
  },[sessions,sessionDays]);
  const teachers=[...new Set(sessions.map(s=>s.teacher))].sort();
  const groups=[...new Map(sessions.filter(s=>s.kind!=="tutoring").map(s=>[keyOf(s),s])).entries()].sort((a,b)=>a[1].level.localeCompare(b[1].level,"es",{numeric:true})||a[1].section.localeCompare(b[1].section));
  const source=(item:TeachingAssignment)=>sessions.find(s=>s.id===item.source_id);
  const visible=items.map((item,index)=>({item,index})).filter(({item})=>{const s=source(item);return s&&keyOf(s)===group;});
  const total=visible.reduce((sum,{item})=>sum+item.weekly_hours,0);
  function patch(index:number,change:Partial<TeachingAssignment>){setItems(old=>old.map((item,i)=>i===index?{...item,...change}:item));setNotice("Hay cambios sin guardar. Guarda las asignaciones antes de generar el horario.");onDirtyChange?.(true);}
  async function save(){
    setError("");setNotice("");
    if(items.some(item=>!item.course.trim()||!item.teacher||!Number.isInteger(item.weekly_hours)||item.weekly_hours<1||item.weekly_hours>30||!item.days.length)){setError("Completa materia, docente, horas enteras de 1 a 30 y al menos un día por asignación.");return;}
    try{await onSave(items,useLoad);setNotice("Asignaciones guardadas en un nuevo conjunto. Genera el horario y revisa el resultado.");}catch(e){setError(e instanceof Error?e.message:"No se pudo guardar el plan.");}
  }
  return <Card id="asignaciones" className="product-card">
    <div className="planning-heading"><div><h2 className="text-xl font-bold flex items-center gap-2"><Users size={21}/> Docentes y materias</h2><p className="muted mt-1">Define las horas semanales de cada materia. Se crearán bloques en distintos días para el mismo paralelo.</p></div><span className="planning-badge">{items.length} asignaciones</span></div>
    <div className="planning-toolbar"><label className="label">Semestre y paralelo<select className="field" value={group} disabled={disabled} onChange={e=>setGroup(e.target.value)}>{groups.map(([key,s])=><option key={key} value={key}>{s.level} · Paralelo {s.section}</option>)}</select></label><div><strong>{total} h de clase por semana</strong><p className="muted">{visible.length} materias · Tutorías se contabilizan aparte</p></div></div>
    <p className="planning-help">Ejemplo: 10 h semanales con bloques de 2 h = 5 clases. La última clase puede ser más corta si hay un resto. Las horas corresponden a esta materia y paralelo.</p>
    <div className="overflow-auto"><table className="teaching-table"><thead><tr><th>Materia</th><th>Docente responsable</th><th>Horas / semana</th><th>Bloque máximo</th><th>Días permitidos</th><th><span className="sr-only">Acciones</span></th></tr></thead><tbody>{visible.map(({item,index})=><tr key={index}>
      <td><input className="field" aria-label={"Materia de asignación "+(index+1)} value={item.course} disabled={disabled} onChange={e=>patch(index,{course:e.target.value})}/></td>
      <td><select className="field" aria-label={"Docente para "+item.course} value={item.teacher} disabled={disabled} onChange={e=>patch(index,{teacher:e.target.value})}>{teachers.map(t=><option key={t}>{t}</option>)}</select></td>
      <td><input className="field" aria-label={"Horas semanales de "+item.course} type="number" min={1} max={30} step={1} value={item.weekly_hours} disabled={disabled} onChange={e=>patch(index,{weekly_hours:Number(e.target.value)})}/></td>
      <td><select className="field" aria-label={"Bloque de "+item.course} value={item.block_hours} disabled={disabled} onChange={e=>patch(index,{block_hours:Number(e.target.value)})}>{[1,2,3,4].map(n=><option key={n} value={n}>{n} h</option>)}</select></td>
      <td><div className="day-pills">{days.map((day,d)=><label key={day}><input type="checkbox" aria-label={day+" para "+item.course} disabled={disabled} checked={item.days.includes(d)} onChange={e=>patch(index,{days:e.target.checked?[...item.days,d].sort():item.days.filter(n=>n!==d)})}/><span>{day}</span></label>)}</div></td>
      <td><button type="button" className="remove-assignment" aria-label={"Quitar asignación de "+item.course} disabled={disabled} onClick={()=>{setItems(old=>old.filter((_,i)=>i!==index));onDirtyChange?.(true);}}><Trash2 size={16}/></button></td>
    </tr>)}</tbody></table></div>
    <div className="planning-actions"><Button variant="outline" type="button" disabled={disabled||!group} onClick={()=>{onDirtyChange?.(true);const s=groups.find(([k])=>k===group)?.[1];if(s)setItems(old=>[...old,{source_id:s.id,course:"Nueva materia",teacher:teachers[0],weekly_hours:4,block_hours:2,days:[0,1,2,3,4]}]);}}><Plus size={16}/> Añadir materia al paralelo</Button><Button type="button" disabled={disabled||!items.length} onClick={()=>void save()}><Save size={16}/> Guardar asignaciones</Button></div>
    <label className="load-option"><input type="checkbox" checked={useLoad} disabled={disabled} onChange={e=>{setUseLoad(e.target.checked);onDirtyChange?.(true);}}/> Usar las horas asignadas de clases y tutorías como meta lectiva de cada docente</label>
    <p className="muted mt-2">Al desmarcar esta opción se conservan las metas registradas. Se guardan todos los paralelos; se mantiene el conjunto anterior. Quitar una materia también retira sus tutorías vinculadas del nuevo plan.</p>
    {error&&<p role="alert" className="planning-error">{error}</p>}{notice&&<p role="status" className="planning-success">{notice}</p>}
  </Card>;
}
