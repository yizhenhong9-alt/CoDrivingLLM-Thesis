"""M24: execute real source methods with stdlib doubles, without simulator/ML imports."""
import ast
import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]


def load(path, names, scope=None, cls=None):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    body = tree.body if cls is None else next(n.body for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == cls)
    nodes = [copy.deepcopy(n) for n in body if isinstance(n, ast.FunctionDef) and n.name in names]
    for node in nodes:
        node.decorator_list = []
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
    scope = {} if scope is None else scope
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), scope)
    return scope


class LabelTests(unittest.TestCase):
    def setUp(self):
        methods = load('highway_env/vehicle/kinematics.py', ['__str__', '__repr__'], cls='Vehicle')
        self.Vehicle = type('MDPVehicle', (), {k: methods[k] for k in ('__str__', '__repr__')})

    def car(self, number):
        car = self.Vehicle()
        car.id, car.position, car.speed = number, [0, 0], 5
        car.lane_index = ('a', 'b', 0)
        return car

    def test_collision_evidence_ids_and_large_ids(self):
        # R6's two addresses share remainder 624; actual string must ignore both.
        self.assertEqual(275988742030624 % 1000, 275988742848624 % 1000)
        cars = [self.car(n) for n in (3, 6, 1003)]
        self.assertEqual([str(v).split(':')[0] for v in cars],
                         ['MDPVehicle #3', 'MDPVehicle #6', 'MDPVehicle #1003'])
        self.assertEqual(repr(cars[0]), str(cars[0]))
        self.assertEqual(str(copy.deepcopy(cars[0])), str(cars[0]))

    def test_unassigned_is_explicit_and_not_a_numeric_label(self):
        car = self.car(3)
        del car.id
        self.assertIn('#unassigned:', str(car))
        self.assertIsNone(re.search(r'MDPVehicle #[0-9]+', str(car)))

    def test_three_create_from_paths_preserve_id(self):
        for path, cls in [('kinematics', 'Vehicle'), ('controller', 'ControlledVehicle'),
                          ('behavior', 'IDMVehicle'), ('uncertainty/prediction', 'IntervalVehicle')]:
            method = load('highway_env/vehicle/' + path + '.py', ['create_from'], cls=cls)['create_from']
            old = NS(id=6, road=object(), position=[1, 2], heading=0, speed=5,
                     target_lane_index=0, target_speed=5, route=[])
            factory = lambda *args, **kwargs: NS()
            self.assertEqual(method(factory, old).id, 6)
            del old.id
            self.assertFalse(hasattr(method(factory, old), 'id'))

    def test_real_string_in_complete_fixture_flow(self):
        from check_qwen_single_step import FlowTests, Vehicle
        from llm_controller.qwen_transport import FixtureReplies
        flow = FlowTests()
        flow.setUp()
        for car in flow.cars:
            car.position = [0, 0]
        method = load('highway_env/vehicle/kinematics.py', ['__str__'], cls='Vehicle')['__str__']
        # Keep actual simulator class spelling used by all original regexes.
        actual_class = type('MDPVehicle', (Vehicle,), {'__str__': method})
        for car in flow.cars:
            car.__class__ = actual_class
        self.assertEqual(flow.run_flow(FixtureReplies('strict')), (1, 1))
        self.assertEqual(flow.report['vehicle_label_version'], 'M24-simulation-id')
        self.assertEqual(flow.steps, [])

    def test_real_negotiation_regex_and_safety_values(self):
        action = load('llm_controller/llm_agent_action.py',
                      ['extract_vehicle_conflicts', 'transfer_negotiation_prompts_to_results'],
                      {'re': re}, 'LlmAgent_action_module')
        agent = NS()
        for name in ('extract_vehicle_conflicts', 'transfer_negotiation_prompts_to_results'):
            setattr(agent, name, action[name].__get__(agent))
        safety = load('llm_controller/prompt_llm.py',
                      ['cal_ttcp', 'check_safety_with_conflict_vehicles'], {'re': re})
        # Choose constant-speed inputs so real cal_ttcp takes its non-numpy branch.
        env = NS(road=NS(network=NS(get_lane=lambda _: NS(speed_limit=5))))
        ego, other = self.car(3), self.car(6)
        group = {'vehicle_i': ego, 'vehicle_j': other,
                 'vehicle_i speed': 5, 'vehicle_j speed': 5,
                 'vehicle_i distance to conflict': 20, 'vehicle_j distance to conflict': 25}
        bridge = json.dumps({'decisions': [{'first_vehicle': 'MDPVehicle #6', 'second_vehicle': 'MDPVehicle #3'}]})
        result = agent.transfer_negotiation_prompts_to_results(ego, bridge)
        self.assertIn('MDPVehicle #6', result)
        actual = safety['check_safety_with_conflict_vehicles'](ego, result, [group], env)
        self.assertEqual(actual[1]['delta ttcp'], 1)
        # Relabel identical physical state and identical specified order.
        ego.id, other.id = 640, 520
        old_result = result.replace('#6', '#520')
        self.assertEqual(actual, safety['check_safety_with_conflict_vehicles'](ego, old_result, [group], env))
        # A different vehicle name must not accidentally select this group.
        wrong = result.replace('#6', '#999')
        self.assertIsNone(safety['check_safety_with_conflict_vehicles'](ego, wrong, [group], env)[1]['delta ttcp'])

    def test_spawn_high_water_mark_and_reset_source(self):
        # Execute actual spawn with deterministic geometry/random doubles.
        vehicle = NS(position=0, plan_route_to=lambda _: None, randomize_behavior=lambda: None)
        class Random:
            def uniform(self): return 0
            def choice(self, *args, **kwargs): return [0, 1]
            def normal(self): return 0
        scope = {'np': NS(linalg=NS(norm=abs)),
                 'utils': NS(class_from_path=lambda _: NS(make_on_lane=lambda *a, **kw: vehicle))}
        spawn = load('highway_env/envs/intersection_env.py', ['_spawn_vehicle'], scope, 'IntersectionEnv')['_spawn_vehicle']
        env = NS(np_random=Random(), road=NS(vehicles=[], next_vehicle_id=7), config={'other_vehicles_type': 'fake'})
        spawn(env)
        self.assertEqual(vehicle.id, 7)
        env.road.vehicles.clear()
        spawn(env)
        self.assertEqual(vehicle.id, 8)
        self.assertEqual(env.road.next_vehicle_id, 9)
        reset = (ROOT / 'highway_env/envs/common/abstract.py').read_text(encoding='utf-8')
        self.assertIn('v.id = i', reset)
        self.assertIn('self.road.next_vehicle_id = len(self.road.vehicles)', reset)


if __name__ == '__main__':
    unittest.main(verbosity=2)
