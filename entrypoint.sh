#!/bin/bash

result=/output/result.xml

function setParameter {
  param_str=""
  if [ $2 != "none" ]; then
    param_str="-$1 $2"
  fi
  echo $param_str
}

allow_level=2

optstring=":i:r:t:p:l:a:"
while getopts ${optstring} arg; do
  case ${arg} in
    i)
      ig=$(setParameter "ig" ${OPTARG})
      ;;
    r)
      if [ ${OPTARG} == "true" ]; then
        recurse="-recurse"
      fi
      ;;
    t)
      tx=$(setParameter "tx" ${OPTARG})
      ;;
    p)
      profile=$(setParameter "profile" ${OPTARG})
      ;;
    l)
      language=$(setParameter "language" ${OPTARG})
      ;;
    a)
      allow_level=${OPTARG}
      ;;
  esac
done
shift $((OPTIND-1))
source=$@

echo "::group::Run the validator"
cd $GITHUB_WORKSPACE
java -jar /tools/validator.jar -version 4.0 $ig $recurse $tx $profile $language -output $result $source
echo "::endgroup::"

python3 /tools/analyze_results.py $result $allow_level
