#!/usr/bin/env bash
set -uo pipefail
cp /mnt/c/Users/gheno/citevision/scripts/_reval_one_alias.sh /home/gheno/citevision-v2/scripts/
sed -i 's/\r$//' /home/gheno/citevision-v2/scripts/_reval_one_alias.sh
for a in red_light phone seatbelt counting; do
  echo "==== START $a ===="
  bash /home/gheno/citevision-v2/scripts/_reval_one_alias.sh "$a"
  echo "==== DONE $a exit=$? ===="
done
echo "ALL_FOUR_DONE"
