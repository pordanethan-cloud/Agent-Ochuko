"""
widget_generator.py — DEPRECATED AND REMOVED.

This module was a fallback code-generation side-car that fired Gemini 2.5 Flash
when the model produced thin widget code. It is no longer needed.

The correct architecture (as of the two-tool widget system):
  1. The model calls visualize__read_me → receives design tokens as a tool result
  2. The model calls visualize__show_widget → produces correct, fully-styled code itself

The read_me design-token injection eliminates the need for a secondary generator.
Importing anything from this module will raise ImportError intentionally.
"""

raise ImportError(
    "widget_generator is deprecated. "
    "Remove all imports of app.services.widget_generator from chat.py. "
    "The visualize__read_me tool handles design token injection natively."
)
