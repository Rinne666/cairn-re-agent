import Editor from '@monaco-editor/react'

const decompiler = `// Artifact preview: decompile 0x401200
bool validate_license(char *input) {
    uint8_t transformed[16];
    for (int i = 0; i < 16; i++) {
        transformed[i] = rol8(input[i] ^ KEY[i], 3);
    }
    return memcmp(transformed, EXPECTED, 16) == 0;
}`

const assembly = `sub_401200:
  push    rbp
  mov     rbp, rsp
  xor     ecx, ecx
.transform:
  movzx   eax, byte ptr [rdi+rcx]
  xor     al, byte ptr [key+rcx]
  rol     al, 3
  mov     byte ptr [rbp+rcx-20h], al
  inc     rcx
  cmp     rcx, 10h
  jne     .transform
  call    memcmp
  ret`

export default function CodePanel({ mode = 'decompiler' }: { mode?: 'decompiler' | 'assembly' }) {
  return (
    <Editor
      height="100%"
      defaultLanguage={mode === 'assembly' ? 'asm' : 'cpp'}
      value={mode === 'assembly' ? assembly : decompiler}
      theme="vs-dark"
      options={{
        readOnly: true,
        minimap: { enabled: false },
        fontFamily: 'Cascadia Code, Consolas, monospace',
        fontSize: 11,
        lineNumbersMinChars: 3,
        scrollBeyondLastLine: false,
        renderLineHighlight: 'none',
        padding: { top: 12 },
        folding: false,
        glyphMargin: false,
        overviewRulerLanes: 0,
      }}
    />
  )
}
