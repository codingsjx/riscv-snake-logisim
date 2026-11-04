"""Expected fixed-map coordinates, used by integration checks and documentation."""
OBSTACLES = ({(x,y) for y in (4,11) for x in (3,4,5,6,10,11,12,13)} |
             {(x,y) for y in (5,6,9,10) for x in (3,12)})
