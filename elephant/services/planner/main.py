import time
import os

def ignite_planner():
    print("--- ELEPHANT PLANNER IS ONLINE ---")
    print(f"Targeting: {os.getenv('ORCHESTRATOR_URI', 'Local Mode')}")
    
    # Simüle edilmiş Task Graph Engine
    def decompose_goal(goal):
        print(f"[PLANNER] Goal Received: {goal}")
        # Bu liste ileride Jules/Claude tarafından dinamik oluşturulacak
        workflow = [
            {"step": 1, "agent": "Researcher", "action": "Deep web search on AI trends"},
            {"step": 2, "agent": "Creator", "action": "Draft strategy paper"},
            {"step": 3, "agent": "Critic", "action": "Tone & Brand alignment check"}
        ]
        return workflow

    # İlk test görevi
    test_goal = "Analyze Fintech 2026 for Salim Gumus"
    plan = decompose_goal(test_goal)
    
    for step in plan:
        print(f"[PLANNER] Dispatching Step {step['step']} to {step['agent']}...")
        time.sleep(2)
        
    print("--- WORKFLOW INITIALIZED SUCCESSFULLY ---")

if __name__ == "__main__":
    ignite_planner()
