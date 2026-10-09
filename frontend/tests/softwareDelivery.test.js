import assert from 'node:assert/strict';
import {test} from 'node:test';
import {attachDocumentDeliverables, presentSoftwareMessage} from '../src/lib/softwareDelivery.js';

const files = [{path:'app/main.py'}, {path:'README.md'}, {path:'.pytest_cache/cache'}, {path:'future.py'}];
const events = [
  {type:'user_message',payload:{content:'Desenvolva uma API Python'}},
  {type:'files_created',payload:{files:files.slice(0,3)}},
  {type:'project_validation_result',payload:{status:'passed'}},
  {type:'assistant_message_done',payload:{content:'```python\nprint("x")\n```'}},
  {type:'user_message',payload:{content:'Pesquise notícias de IA'}},
];
const message = {role:'assistant',final:true,eventIndex:3,prompt:'Desenvolva uma API Python',content:events[3].payload.content};

test('legacy software is compacted using its own delivery evidence', () => {
  const presented = presentSoftwareMessage(message, files, events);
  assert.ok(!presented.content.includes('```'));
  assert.ok(presented.content.includes('2 arquivos'));
  assert.ok(presented.content.includes('aprovada'));
  assert.ok(!presented.archive);
  assert.equal(message.content, events[3].payload.content);
});
test('explicit snippets, streaming and research are preserved', () => {
  for (const sample of [{...message,prompt:'Mostre um trecho de código Python'}, {...message,final:false}, {...message,prompt:'Pesquise notícias de IA'}, {...message,delivery:{kind:'software'}}]) {
    assert.equal(presentSoftwareMessage(sample, files, events), sample);
  }
});
test('missing files do not become a claimed delivery', () => {
  assert.equal(presentSoftwareMessage(message, [], events), message);
});
test('later validation cannot prove an earlier delivery', () => {
  const noValidation = events.map((event) => event.type === 'project_validation_result' ? {type:'agent_progress',payload:{}} : event);
  noValidation.push({type:'project_validation_result',payload:{status:'passed'}});
  const presented = presentSoftwareMessage(message, files, noValidation);
  assert.ok(presented.content.includes('não há uma verificação'));
});

test('attachDocumentDeliverables attaches generated PDF and download to assistant message', () => {
  const docFiles = [
    {path: 'ultimas_noticias_ia.pdf', size_bytes: 36811},
    {path: 'gerar_pdf.py', size_bytes: 1200},
  ];
  const docEvents = [
    {type: 'user_message', payload: {content: 'ultimas noticias de inteligencia artificial em formato pdf'}},
    {type: 'files_created', payload: {files: [{path: 'ultimas_noticias_ia.pdf'}]}},
    {type: 'assistant_message_done', payload: {content: 'Aqui está o resumo das notícias em formato PDF: `ultimas_noticias_ia.pdf`.'}},
  ];
  const docMsg = {
    role: 'assistant',
    final: true,
    eventIndex: 2,
    prompt: 'ultimas noticias de inteligencia artificial em formato pdf',
    content: 'Aqui está o resumo das notícias em formato PDF: `ultimas_noticias_ia.pdf`.',
  };

  const enriched = attachDocumentDeliverables(docMsg, docFiles, docEvents);
  assert.ok(Array.isArray(enriched.documents));
  assert.equal(enriched.documents.length, 1);
  assert.equal(enriched.documents[0].path, 'ultimas_noticias_ia.pdf');
  assert.equal(enriched.documents[0].kind, 'pdf');
  assert.equal(enriched.documents[0].primary, true);
  assert.equal(enriched.documents[0].previewable, true);

  assert.ok(Array.isArray(enriched.downloads));
  assert.equal(enriched.downloads.length, 1);
  assert.equal(enriched.downloads[0].path, 'ultimas_noticias_ia.pdf');
});

test('attachDocumentDeliverables preserves existing documents without duplicate', () => {
  const docFiles = [{path: 'relatorio.pdf', size_bytes: 2048}];
  const docEvents = [
    {type: 'user_message', payload: {content: 'gere um relatorio pdf'}},
    {type: 'assistant_message_done', payload: {content: 'relatorio pronto'}},
  ];
  const docMsg = {
    role: 'assistant',
    final: true,
    eventIndex: 1,
    content: 'relatorio pronto em relatorio.pdf',
    documents: [{path: 'relatorio.pdf', kind: 'pdf', primary: true}],
    downloads: [{path: 'relatorio.pdf'}],
  };

  const enriched = attachDocumentDeliverables(docMsg, docFiles, docEvents);
  assert.equal(enriched.documents.length, 1);
  assert.equal(enriched.downloads.length, 1);
});
