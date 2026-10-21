# Tree view and configuration editor: design brief

Any tree view or configuration editor in this library is built to this brief.

## The idea

Classic Qt / Windows 98 tree views and configuration editors: exemplary
presentation of hierarchical information. Tight row spacing, compact
indentation, explicit tree connectors, small expand/collapse controls, aligned
columns, and exceptional information density.

The point is not an old-fashioned interface. It is the spatial efficiency and
structural precision that older desktop interfaces often had.

## Bad and good

| | Bad | Good |
|---|---|---|
| Row height | Excessively tall | Compact |
| Indentation | Large, wasteful | Tight, incremental |
| Typography | Oversized | Small, functional |
| Hierarchy | Visually loose | Explicit parent-child structure |
| Expand/collapse | Large chevrons | Tiny +/- controls |
| Tree connectors | Mostly absent | Visible dotted guide lines |
| Information density | Low | Very high |
| Screen utilization | Lots of empty space | Many entries visible |
| Overall feel | Touch-oriented interface | Precision desktop instrument |
| Sorting | A fixed order, or a sort that scatters groups | A header click sorts siblings, groups stay together; numbers as numbers, empty values last |
