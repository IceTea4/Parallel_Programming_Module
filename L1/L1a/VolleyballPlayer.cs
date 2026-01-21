using System.Runtime.Serialization;

namespace L1a
{
    [DataContract]
	public class VolleyballPlayer
	{
        [DataMember(Name = "name")]
        public string Name { get; set; }

        [DataMember(Name = "games")]
        public int Games { get; set; }

        [DataMember(Name = "winning")]
        public double Winning { get; set; }

        public override string ToString()
        {
            return string.Format("{0,-20} | {1,8} | {2,10:F2}",
                Name, Games, Winning);
        }
	}

    [DataContract]
    public class PlayersWrapper
    {
        [DataMember(Name = "player")]
        public List<VolleyballPlayer> Player { get; set; }
    }
}

