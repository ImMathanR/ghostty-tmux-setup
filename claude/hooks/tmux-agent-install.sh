#!/bin/sh
# Layers the agent display onto whatever tmux config loaded us, without
# replacing its look: plain tabs keep the host's own formats, status-right
# keeps its contents (tas keeps continuum's auto-save there), and only panes
# whose command is a bare version number (Claude's process name) get renamed
# after their folder. Safe to run again on every config reload.

wrap() {  # wrap <option> <saved-as>
  cur=$(tmux show -gv "$1")
  case "$cur" in
    *@agent_fmt*) ;;  # already wrapped
    *) tmux set -g "$2" "$cur"
       tmux set -g "$1" "#{?#{@agent_fmt},#{@agent_fmt},#{E:$2}}" ;;
  esac
}
wrap window-status-format @agent_plain_fmt
wrap window-status-current-format @agent_plain_current_fmt

right=$(tmux show -gv status-right)
case "$right" in
  *@agent_score*) ;;
  *) right="#{@agent_score}$right" ;;
esac
case "$right" in  # a clickable map button (birdseye) in front of the scoreboard
  *birdseye*) ;;
  *) right="#[range=user|birdseye]#[fg=#8a8a8d] ▦ #[norange]#[default] $right" ;;
esac
tmux set -g status-right "$right"
[ "$(tmux show -gv status-right-length)" -lt 80 ] 2>/dev/null && tmux set -g status-right-length 80

name=$(tmux show -gwv automatic-rename-format)
case "$name" in
  *pane_current_command}},#{b:pane_current_path}*) ;;
  *) tmux set -gw automatic-rename-format \
       "#{?#{m/r:^[0-9]+[.][0-9]+[.][0-9]+\$,#{pane_current_command}},#{b:pane_current_path},$name}" ;;
esac
# a focused sidebar (sidebar/) keeps its window's name rather than naming it after python
name=$(tmux show -gwv automatic-rename-format)
case "$name" in
  *@sidebar*) ;;
  *) tmux set -gw automatic-rename-format "#{?#{@sidebar},#{window_name},$name}" ;;
esac
exit 0
