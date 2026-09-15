import { test } from 'node:test';
import assert from 'node:assert/strict';
import { transitRoutes, sortTransit, transitStops, segmentLabel } from '../src/components/map/transit.ts';

test('incomplete/intercity responses never become complete route cards', () => {
  const route = { complete: true, segments: [] };
  assert.deepEqual(transitRoutes({ mode: 'transit', success: false, items: [route] }), []);
  assert.deepEqual(transitRoutes({ mode: 'driving', items: [route] }), []);
  assert.deepEqual(transitRoutes({ mode: 'transit', items: [{ complete: false }] }), []);
});
test('sorting preserves route identity and does not mutate server order', () => {
  const routes = [{route_index: 4, duration_min: 40, transfer_count: 0, walking_distance_m: 500},
    {route_index: 7, duration_min: 30, transfer_count: 1, walking_distance_m: 800}];
  assert.equal(sortTransit(routes, 'duration_min')[0].route_index, 7);
  assert.equal(sortTransit(routes, 'transfer_count')[0].route_index, 4);
  assert.equal(routes[0].route_index, 4);
});
test('stops accept provider coordinate strings and reject invalid coordinates', () => {
  const route = {segments:[{trafficType:1, startX:127, startY:37, startName:'승차',
    passStopList:{stations:[{x:'127',y:'37',stationName:'중복'}, {x:'128',y:'38',stationName:'경유'}, {x:'',y:''}, {x:'nan',y:38}]},
    endX:128,endY:38,endName:'하차'}]};
  assert.deepEqual(transitStops(route).map((s) => [s.lat,s.lng]), [[37,127],[38,128]]);
});
test('bus number, subway line and walk labels remain distinct', () => {
  assert.equal(segmentLabel({trafficType:2,lane:[{busNo:'402'},{busNo:'405'}]}),'402 / 405');
  assert.equal(segmentLabel({trafficType:1,lane:[{name:'2호선'}]}),'2호선');
  assert.equal(segmentLabel({trafficType:3}),'도보');
});
