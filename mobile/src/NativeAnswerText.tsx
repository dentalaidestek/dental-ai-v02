import React from 'react';
import {ScrollView,StyleSheet,Text,View} from 'react-native';
// Native text and horizontally scrollable tables; server content is never executed.
function Inline({value}:{value:string}){return <Text selectable style={s.body}>{value.split(/(\*\*[^*]+\*\*)/g).map((part,n)=>part.startsWith('**')?<Text key={n} style={{fontWeight:'800'}}>{part.slice(2,-2)}</Text>:part)}</Text>}
export default function NativeAnswerText({value}:{value:string}){
 const lines=value.replace(/<!--ACADEMIC_[\s\S]*?-->/g,'').split('\n'),blocks:React.ReactNode[]=[];
 for(let i=0;i<lines.length;i++){
  const line=lines[i];
  if(line.trim().startsWith('|')&&/^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$/.test(lines[i+1]||'')){
   const rows=[line];i++;while(i+1<lines.length&&lines[i+1].trim().startsWith('|'))rows.push(lines[++i]);
   blocks.push(<ScrollView key={i} horizontal accessibilityLabel="Kaydırılabilir kaynak tablosu"><View style={s.table}>{rows.map((row,n)=><View key={n} style={s.row}>{row.replace(/^\s*\||\|\s*$/g,'').split('|').map((cell,c)=><View key={c} style={[s.cell,n===0&&s.header]}><Inline value={cell.trim()}/></View>)}</View>)}</View></ScrollView>);continue;
  }
  const heading=/^(#{1,4})\s+(.+)$/.exec(line);if(heading){blocks.push(<Text key={i} accessibilityRole="header" style={[s.heading,{fontSize:heading[1].length<3?19:16}]}>{heading[2]}</Text>);continue}
  if(line.trim())blocks.push(<Inline key={i} value={line.replace(/^\s*[-*]\s+/,'• ')}/>);
 }
 return <View style={{gap:7}}>{blocks}</View>
}
const s=StyleSheet.create({body:{fontSize:15,lineHeight:24,color:'#102033'},heading:{fontWeight:'800',color:'#102033',marginTop:10},table:{borderWidth:1,borderColor:'#DCE3EB',marginVertical:8},row:{flexDirection:'row'},cell:{width:180,padding:10,borderRightWidth:1,borderBottomWidth:1,borderColor:'#DCE3EB'},header:{backgroundColor:'#EDF3FA'}});
