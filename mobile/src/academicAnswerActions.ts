import type {Message} from './academicApi';
import type {AcademicVote} from './academicApi';

export function normalizeAcademicVote(value:unknown):AcademicVote{
 return value==='like'||value==='dislike'?value:'none';
}

export function toggleAcademicVote(current:unknown,selected:'like'|'dislike'):AcademicVote{
 return normalizeAcademicVote(current)===selected?'none':selected;
}

export function academicAnswerShareText(message:Pick<Message,'content'|'quiz'>):string{
 const content=typeof message.content==='string'?message.content.trim():'';
 if(content)return content;
 const questions=message.quiz?.questions;
 if(!Array.isArray(questions))return '';
 return questions.map(question=>[
  String(question.number)+'. '+question.stem,
  ...question.options.map((option,index)=>(['A','B','C','D','E'][index]||'?')+') '+option),
 ].join('\n')).join('\n\n').trim();
}
