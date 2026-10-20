import streamlit as st
import pandas as pd
import random
from datetime import datetime
import json
from pathlib import Path

# Page configuration
st.set_page_config(page_title="Dartboard Bracket", layout="wide")

# ============================================================================
# HELPER FUNCTIONS (from notebook)
# ============================================================================

def get_win_probabilities(team1, team2, rankings):
    """Calculate win probabilities based on rankings."""
    team1_total = rankings.loc[team1]['Seed'] * 4 + rankings.loc[team1]['Ken Pom'] + rankings.loc[team1]['Off Eff'] + rankings.loc[team1]['Def Eff'] + rankings.loc[team1]['NET Ranking']
    team2_total = rankings.loc[team2]['Seed'] * 4 + rankings.loc[team2]['Ken Pom'] + rankings.loc[team2]['Off Eff'] + rankings.loc[team2]['Def Eff'] + rankings.loc[team2]['NET Ranking']
    total = team1_total + team2_total
    team1_prob = 1 - (team1_total * 1.0 / total)
    team2_prob = 1 - (team2_total * 1.0 / total)
    return team1_prob, team2_prob


def get_dartboard_numbers(team1, team2, rankings, dartboard_numbers, dartboard_weights,
                          n_trials=2000, temperature=0.35, seed=None):
    """Assign dartboard numbers to teams based on win probabilities."""
    if seed is not None:
        random.seed(seed)

    team1_prob, team2_prob = get_win_probabilities(team1, team2, rankings)
    total_weight = sum(dartboard_weights[n] for n in dartboard_numbers)
    team1_target = total_weight * team1_prob

    best = None

    for _ in range(n_trials):
        nums = dartboard_numbers[:]
        random.shuffle(nums)

        assignments = {}
        w1 = 0
        w2 = 0

        for n in nums:
            w = dartboard_weights[n]
            need1 = team1_target - w1
            need2 = (total_weight - team1_target) - w2

            x = (need1 - need2) / max(1.0, temperature * total_weight)
            p_team1 = 1.0 / (1.0 + (2.718281828 ** (-x)))

            if random.random() < p_team1:
                assignments[n] = team1
                w1 += w
            else:
                assignments[n] = team2
                w2 += w

        score = abs(w1 - team1_target)

        if best is None or score < best[0] or (score == best[0] and random.random() < 0.5):
            best = (score, assignments, w1, w2)

    _, assignments, w1, w2 = best
    team_list = pd.Series(assignments).sort_index()
    
    return team_list, team1_prob, team2_prob


# ============================================================================
# INITIALIZE SESSION STATE
# ============================================================================

if "initialized" not in st.session_state:
    st.session_state.initialized = False
    st.session_state.rankings = None
    st.session_state.dartboard_numbers = None
    st.session_state.dartboard_weights = None
    st.session_state.bracket_rounds = None
    st.session_state.current_round = 0
    st.session_state.current_matchup = 0
    st.session_state.tournament_log = []
    st.session_state.results = {}  # Store results by round
    st.session_state.log_file = None  # Path to timestamped log file
    st.session_state.previous_state = None  # For undo functionality


def initialize_app():
    """Initialize the app with rankings and dartboard setup."""
    if st.session_state.initialized:
        return

    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"bracket_results_{timestamp}.txt"
    log_path = Path(log_filename)
    
    with open(log_path, "w") as f:
        f.write(f"Dartboard Bracket Tournament Log\n")
        f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
    
    st.session_state.log_file = log_path

    # Load rankings
    rankings = pd.read_csv("CBB Rankings - 2026.csv")
    rankings.set_index("Team", inplace=True)
    st.session_state.rankings = rankings

    # Dartboard setup
    dartboard_numbers = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
    descending = [7, 6, 5, 5, 4, 3]
    ascending = [4, 5, 5, 6]
    weights_list = descending + ascending + descending + ascending
    dartboard_weights = {num: weight for num, weight in zip(dartboard_numbers, weights_list)}
    
    st.session_state.dartboard_numbers = dartboard_numbers
    st.session_state.dartboard_weights = dartboard_weights

    # Create initial bracket from first 64 teams
    bracket_first_round = rankings.index.tolist()[:64]
    st.session_state.bracket_rounds = [bracket_first_round]
    
    st.session_state.current_round = 0
    st.session_state.current_matchup = 0
    st.session_state.tournament_log = []
    st.session_state.results = {0: []}
    
    st.session_state.initialized = True


# ============================================================================
# MAIN APP
# ============================================================================

st.title("🎯 Dartboard Bracket Tournament")

# Initialize on first load
initialize_app()

# ============================================================================
# SIDEBAR - TOURNAMENT STATUS
# ============================================================================

with st.sidebar:
    st.header("Tournament Status")
    
    round_names = ["Round of 64", "Round of 32", "Sweet 16", "Elite 8", "Final 4", "Championship", "Champion"]
    
    if st.session_state.current_round < len(st.session_state.bracket_rounds):
        round_name = round_names[st.session_state.current_round]
        matchup_num = st.session_state.current_matchup + 1
        total_matchups = len(st.session_state.bracket_rounds[st.session_state.current_round]) // 2
        
        st.metric("Current Round", round_name)
        st.metric("Matchup", f"{matchup_num} of {total_matchups}")
    else:
        st.success("✅ Tournament Complete!")
    
    st.divider()
    st.subheader("Tournament Log")
    if st.session_state.tournament_log:
        for log_entry in st.session_state.tournament_log[-10:]:  # Last 10 entries
            st.text(log_entry)
    else:
        st.text("No results yet...")

# ============================================================================
# MAIN CONTENT - MATCHUP OR RESULTS
# ============================================================================

if st.session_state.current_round >= len(st.session_state.bracket_rounds):
    # Tournament complete - show champion
    st.success("🏆 Tournament Complete!")
    if st.session_state.bracket_rounds[-1]:
        champion = st.session_state.bracket_rounds[-1][0]
        st.markdown(f"## **Champion: {champion}**")
        
        # Write champion to file
        with open(st.session_state.log_file, "a") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"CHAMPION: {champion}\n")
            f.write(f"Tournament Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    st.divider()
    st.subheader("Tournament Summary")
    
    if st.session_state.tournament_log:
        log_text = "\n".join(st.session_state.tournament_log)
        st.text_area("Full Log", log_text, height=400, disabled=True)
        
        # Offer to view/download the saved file
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"📁 Log saved to: `{st.session_state.log_file.name}`")
        
        with col2:
            if st.button("🔄 Start New Tournament", type="secondary"):
                # Reset session state
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

else:
    # Show current matchup
    current_bracket = st.session_state.bracket_rounds[st.session_state.current_round]
    matchup_idx = st.session_state.current_matchup * 2
    
    # Check if there are enough teams for this matchup
    if matchup_idx + 1 >= len(current_bracket):
        # Tournament is complete
        st.success("🏆 Tournament Complete!")
        if current_bracket:
            champion = current_bracket[0]
            st.markdown(f"## **Champion: {champion}**")
            
            # Write champion to file
            with open(st.session_state.log_file, "a") as f:
                f.write("\n" + "=" * 60 + "\n")
                f.write(f"CHAMPION: {champion}\n")
                f.write(f"Tournament Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        st.divider()
        if st.button("🔄 Start New Tournament", type="primary"):
            # Reset session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    else:
        # Show the matchup
        team1 = current_bracket[matchup_idx]
        team2 = current_bracket[matchup_idx + 1]
        # Show the matchup
        team1 = current_bracket[matchup_idx]
        team2 = current_bracket[matchup_idx + 1]
        
        st.subheader(f"🎯 {round_names[st.session_state.current_round]}")
        
        # Get dartboard numbers and probabilities
        dartboard_assignment, team1_prob, team2_prob = get_dartboard_numbers(
            team1, team2,
            st.session_state.rankings,
            st.session_state.dartboard_numbers,
            st.session_state.dartboard_weights,
            seed=None
        )
        
        # Display matchup with dartboard numbers
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"### {team1}")
            st.metric("Win Probability", f"{team1_prob:.1%}")
            st.subheader("Dartboard Numbers")
            team1_numbers = dartboard_assignment[dartboard_assignment == team1].index.tolist()
            st.write(", ".join(map(str, sorted(team1_numbers))))
            
        with col2:
            st.markdown(f"### {team2}")
            st.metric("Win Probability", f"{team2_prob:.1%}")
            st.subheader("Dartboard Numbers")
            team2_numbers = dartboard_assignment[dartboard_assignment == team2].index.tolist()
            st.write(", ".join(map(str, sorted(team2_numbers))))
        
        st.divider()
        
        # Input for number thrown - Button Grid
        st.subheader("📌 Select the dart number thrown")
        
        # Create 5 rows of 4 buttons for dartboard numbers 1-20
        cols = st.columns(5)
        number_clicked = None
        
        for i, num in enumerate(range(1, 21)):
            col_idx = i % 5
            team = dartboard_assignment[num]
            button_label = f"{num} - {team}"
            with cols[col_idx]:
                if st.button(button_label, use_container_width=True, key=f"dart_{num}_{st.session_state.current_round}_{st.session_state.current_matchup}"):
                    number_clicked = num
        
        # Undo button
        st.divider()
        if st.session_state.tournament_log:
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("↶ Undo", type="secondary", use_container_width=True):
                    if st.session_state.previous_state:
                        # Restore previous state
                        prev = st.session_state.previous_state
                        st.session_state.current_round = prev['round']
                        st.session_state.current_matchup = prev['matchup']
                        st.session_state.results = prev['results']
                        st.session_state.bracket_rounds = prev['bracket_rounds']
                        st.session_state.previous_state = None
                        
                        # Remove last log entry
                        last_log = st.session_state.tournament_log.pop()
                        
                        # Remove from file
                        with open(st.session_state.log_file, "r") as f:
                            lines = f.readlines()
                        
                        # Remove the last entry line
                        if lines and lines[-1].strip() == last_log:
                            lines.pop()
                        
                        with open(st.session_state.log_file, "w") as f:
                            f.writelines(lines)
                        
                        st.success(f"✅ Undid: {last_log}")
                        st.rerun()
        
        # Process the number if clicked
        if number_clicked is not None:
            if number_clicked in dartboard_assignment.index:
                # Save current state before recording
                st.session_state.previous_state = {
                    'round': st.session_state.current_round,
                    'matchup': st.session_state.current_matchup,
                    'results': {k: v[:] for k, v in st.session_state.results.items()},  # Deep copy
                    'bracket_rounds': [r[:] if isinstance(r, list) else r for r in st.session_state.bracket_rounds]  # Deep copy
                }
                
                winner = dartboard_assignment[number_clicked]
                
                # Log the result
                round_name = round_names[st.session_state.current_round]
                log_entry = f"{round_name} - {team1} vs {team2}: Dart #{number_clicked} → {winner} wins"
                st.session_state.tournament_log.append(log_entry)
                
                # Write to file
                with open(st.session_state.log_file, "a") as f:
                    f.write(log_entry + "\n")
                
                # Add winner to results
                if st.session_state.current_round + 1 not in st.session_state.results:
                    st.session_state.results[st.session_state.current_round + 1] = []
                st.session_state.results[st.session_state.current_round + 1].append(winner)
                
                # Move to next matchup or round
                st.session_state.current_matchup += 1
                
                # Check if round is complete
                if st.session_state.current_matchup * 2 >= len(current_bracket):
                    # Move to next round
                    next_round_teams = st.session_state.results[st.session_state.current_round + 1]
                    st.session_state.bracket_rounds.append(next_round_teams)
                    st.session_state.current_round += 1
                    st.session_state.current_matchup = 0
                
                st.rerun()
            else:
                st.error(f"❌ Number {number_clicked} is not assigned to either team. Please try again.")

# ============================================================================
# FOOTER
# ============================================================================

st.divider()
st.caption("🎯 Dartboard Bracket v1.0 | CBB Tournament 2026")
