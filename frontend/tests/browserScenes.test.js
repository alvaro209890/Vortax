import assert from 'node:assert/strict';
import {test} from 'node:test';
import {isBrowserScene, browserScene, cursorPosition} from '../src/lib/browserScenes.js';
test('blank captures never replace a real page', () => {
  assert.equal(isBrowserScene({type:'screen_frame',payload:{url:'about:blank',image_base64:'jpeg'}}), false);
  assert.equal(isBrowserScene({type:'screen_frame',payload:{url:'https://example.com',image_base64:'jpeg'}}), true);
});
test('HTTP search and blocked screen participate in replay', () => {
  assert.equal(isBrowserScene({type:'browser_view'}), true);
  const scene = browserScene({type:'screen_frame_blocked',payload:{image_base64:'should-not-show'}});
  assert.equal(scene.blocked, true);
  assert.equal(scene.image, null);
});
test('pointer scales against captured viewport on mobile and desktop', () => {
  assert.deepEqual(cursorPosition({x:683,y:384},{width:1366,height:768}),{x:50,y:50});
  assert.equal(cursorPosition({x:2,y:3},null),null);
  assert.equal(cursorPosition({x:NaN,y:3},{width:100,height:100}),null);
});
