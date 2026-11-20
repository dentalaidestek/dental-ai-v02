import React from 'react';
import {Pressable,StyleSheet,Text,TextInput,View} from 'react-native';

type Props={
  value:string;
  onChangeText:(value:string)=>void;
  onSend:()=>void;
  disabled?:boolean;
};

export default function NativeAcademicComposer({value,onChangeText,onSend,disabled=false}:Props){
  const canSend=!disabled&&value.trim().length>0;
  return <View style={s.footer}>
    <View style={s.composer}>
      <TextInput
        accessibilityLabel="Akademik soru"
        accessibilityHint="Ders notlarına göre sorunuzu yazın."
        value={value}
        onChangeText={onChangeText}
        maxLength={8000}
        multiline
        editable={!disabled}
        placeholder="Mesajını yaz..."
        placeholderTextColor="#9AA0AA"
        textAlignVertical="top"
        style={s.input}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Akademik soruyu gönder"
        accessibilityState={{disabled:!canSend}}
        disabled={disabled}
        onPress={()=>{if(canSend)onSend()}}
        style={[s.send,!canSend&&s.sendDisabled]}
      >
        <Text style={s.sendText}>Gönder</Text>
      </Pressable>
    </View>
  </View>;
}

const s=StyleSheet.create({
  footer:{flexShrink:0,paddingHorizontal:10,paddingTop:8,paddingBottom:8,borderTopWidth:1,borderTopColor:'#E8EAEE',backgroundColor:'#FFFFFF'},
  composer:{width:'100%',maxWidth:820,alignSelf:'center',flexDirection:'row',alignItems:'flex-end',gap:8,padding:6,borderWidth:1,borderColor:'#CFD4DC',borderRadius:17,backgroundColor:'#FFFFFF'},
  input:{flex:1,minHeight:42,maxHeight:140,paddingHorizontal:10,paddingVertical:9,fontSize:14,lineHeight:20,color:'#111827',backgroundColor:'#FFFFFF'},
  send:{minWidth:44,minHeight:42,paddingHorizontal:12,borderRadius:12,backgroundColor:'#111827',alignItems:'center',justifyContent:'center'},
  sendDisabled:{backgroundColor:'#D1D5DB'},
  sendText:{color:'#FFFFFF',fontSize:13,fontWeight:'800'}
});
