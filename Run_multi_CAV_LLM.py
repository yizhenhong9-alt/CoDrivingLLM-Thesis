"""Original project entry: explicit Qwen integration or preserved cloud loop.

Qwen uses an already-running Spark loopback API; it never starts a model.
"""
MEMORY_MODE = "off"


def legacy_main():
    from llm_controller.llm_agent_action import LlmAgent_action_module
    import gym
    from llm_controller.llm_agent_negotiation_system import LlmAgent_negotiation_module  # system perspective negotiation
    from llm_controller.memory_mode import create_memory
    import highway_env
    import imageio
    import openpyxl
    import os
    import shutil

    # M04: off performs no memory construction or embedding/vector-store import.
    # The original cloud-backed memory implementation is retained in memory.py.


    def open_excel(i):
        file_dir = './llm_controller/excel/' + '/'
        file_name = file_dir + str(i) + '.xlsx'

        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
        workbook = openpyxl.Workbook()
        if os.path.exists(file_name):
            workbook = openpyxl.load_workbook(file_name)

        # if 'Sheet' in workbook.sheetnames:
        #     del workbook['Sheet']
        return file_name, workbook

    def write_data(workbook, env, t):
        column_names = ['t', 'x', 'y', 'v', 'theta', 'background_veh?']
        for vehicle in env.road.vehicles:
            sheet_name = str(vehicle.id)
            if sheet_name not in workbook.sheetnames:
                worksheet = workbook.create_sheet(sheet_name)
                worksheet.append(column_names)
            else:
                worksheet = workbook[sheet_name]
            controlled_vehicles = env.controlled_vehicles
            if vehicle not in controlled_vehicles:
                background_vehicles = False
            else:
                background_vehicles = True
            state = [round(vehicle.position[0], 2), round(vehicle.position[1], 2), round(vehicle.speed, 2), round(vehicle.heading, 2), background_vehicles]
            row_data = [t, round(vehicle.position[0], 2), round(vehicle.position[1], 2), round(vehicle.speed, 2), round(vehicle.heading, 2), background_vehicles]
            worksheet.append(row_data)
            worksheet.cell(row=t + 2, column=1, value=t)
            for i, item in enumerate(state):
                worksheet.cell(row=t + 2, column=i + 2, value=item)
        return workbook

    # if choose merge, active config
    # config = {
    #     "simulation_frequency": 20,
    #     "policy_frequency": 5,
    #     "duration":40
    # }

    # env = gym.make('merge-multi-agent-v0', config=config)
    env = gym.make('intersection-multi-agent-v0')
    # env = gym.make('highway-v0')


    for i in range(100):
        video_path = './llm_controller/video/' + str(i) + '.mp4'
        writer = imageio.get_writer(video_path, fps=30)
        file_name, workbook = open_excel(i)
        terminated = False
        t = 0
        obs = env.reset()
        while not (terminated):
            print('---------------------------------------------------------------')
            # memory module
            memory = create_memory(env, mode=MEMORY_MODE)

            # negotiation module
            llm_agent_conflict_resolver = LlmAgent_negotiation_module(env)  # system perspective negotiation
            negotiation_prompt, conflicting_info = llm_agent_conflict_resolver.llm_controller_run(env)

            # decision
            llm_agent = LlmAgent_action_module(env)
            sce = llm_agent.retrun_sce()  # sce data
            llm_actions = llm_agent.llm_controller_run(env, negotiation_prompt, conflicting_info, env.controlled_vehicles, memory)  # negotiation results from upper layer and conflict info which stores distance speed


            action = [item for sublist in llm_actions for item in sublist]  # [[1], [3]]->[1, 3]

            for veh in env.controlled_vehicles:
                print(veh, veh.speed)

            obs, global_reward, terminated, info = env.step(tuple(action), env)
            env.render()
            print("llm_actions:", action)
            print("global_reward_llm:", global_reward)

            frame = env.render('rgb_array')
            writer.append_data(frame)

            workbook = write_data(workbook, env, t)
            workbook.save(file_name)
            t += 1

            # action = [1,3,1,3]  # env.action_space.sample()
            # obs, reward, terminated, info = env.step(tuple(action), env)
            # print(action)
            # print(terminated, info)
            env.render()
        writer.close()
        print(i)



def main(argv=None):
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("qwen", "legacy"), required=True)
    parser.add_argument("--parser", choices=("strict", "legacy"), default="strict")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--wall-seconds", type=float, default=1800)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument('--memory', choices=('off', 'on'), default='off')
    parser.add_argument('--memory-config', type=Path)
    args = parser.parse_args(argv)
    if args.backend == "legacy":
        # Preserve original 100-episode cloud/video/Excel behavior.
        if argv is None:
            import sys
            tokens = sys.argv[1:]
        else:
            tokens = argv
        if tokens != ["--backend", "legacy"]:
            parser.error("Legacy accepts only --backend legacy; Qwen options do not apply")
        return legacy_main()
    if args.output_dir is None:
        parser.error("Qwen requires --output-dir under /home/nclab/Yizhen")
    if args.memory == 'on' and (args.memory_config is None or args.parser != 'strict'):
        parser.error('memory on requires explicit --memory-config and strict parser')
    if args.memory == 'off' and args.memory_config is not None:
        parser.error('Omit --memory-config with memory off')
    from llm_controller.qwen_episode import main as qwen_main
    return qwen_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
