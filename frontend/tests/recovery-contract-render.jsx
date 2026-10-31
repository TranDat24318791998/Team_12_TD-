import assert from 'node:assert/strict';
import {renderToStaticMarkup} from 'react-dom/server';
import {DemoPage} from '../src/pages/Demo.jsx';
const noop=()=>{};
export function verify(data){
  const render=(state,events)=>renderToStaticMarkup(<DemoPage run={{state,events,act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  const before=render(data.before,data.events_before);
  assert.ok(before.includes('Xem lại gói trước'));
  assert.ok(before.includes('Chưa có gói điều chỉnh.'));
  assert.ok(!before.includes('data-night'));
  const after=render(data.after,data.events_after);
  assert.equal(data.response.restoration_status,'restored');
  assert.equal(data.after.pending_card.card_id,data.response.restored_card_id);
  assert.deepEqual(data.after.pending_card.package,data.original.package);
  assert.ok(after.includes('Gói trước vẫn còn hiệu lực'));
  assert.ok(after.includes('data-decision="accept"') && after.includes('data-decision="reject"'));
  assert.ok(!after.includes('data-night'));
}
