/* Shared source of truth for the replay and the two-player table.
   Generated pages inline this file; do not edit the generated HTML. */
"use strict";

/* ═══════════════════════════════════════════════════════════════
   CARD DATA — Oracle text, mana cost and P/T from Scryfall.
   `plain` is a one-line beginner gloss written for this replay.
   `frame` picks the card colour: W U B R G M(ulticolour) A(rtifact) L(and)
   ═══════════════════════════════════════════════════════════════ */
const CARDS = {
  "Watchwolf":{cost:"{G}{W}",type:"Creature — Wolf",pt:"3/3",frame:"M",
    text:"",plain:"Three mana of stats for two mana. Nothing else — it just hits hard, early."},
  "Kird Ape":{cost:"{R}",type:"Creature — Ape",pt:"1/1",frame:"R",
    text:"This creature gets +1/+2 as long as you control a Forest.",
    plain:"A 1-mana 2/3 if you have a Forest out — one of the best rates ever printed."},
  "Isamaru, Hound of Konda":{cost:"{W}",type:"Legendary Creature — Dog",pt:"2/2",frame:"W",
    text:"",plain:"A 2/2 for one mana. Pure speed."},
  "Savannah Lions":{cost:"{W}",type:"Creature — Cat",pt:"2/1",frame:"W",
    text:"",plain:"A 2/1 for one mana."},
  "Bathe in Light":{cost:"{1}{W}",type:"Instant",pt:"",frame:"W",
    text:"Radiance — Choose a color. Target creature and each other creature that shares a color with it gain protection from the chosen color until end of turn.",
    plain:"Name black, and every white creature you have becomes unblockable by black creatures for the turn."},
  "Char":{cost:"{2}{R}",type:"Instant",pt:"",frame:"R",
    text:"Char deals 4 damage to any target and 2 damage to you.",
    plain:"Four damage anywhere — but it also burns you for two. That two matters here."},
  "Lightning Helix":{cost:"{R}{W}",type:"Instant",pt:"",frame:"M",
    text:"Lightning Helix deals 3 damage to any target and you gain 3 life.",
    plain:"Three damage to anything, and you gain three life. Four copies in the deck."},
  "Shock":{cost:"{R}",type:"Instant",pt:"",frame:"R",
    text:"Shock deals 2 damage to any target.",plain:"Two damage for one mana."},
  "Guerrilla Tactics":{cost:"{1}{R}",type:"Instant",pt:"",frame:"R",
    text:"Guerrilla Tactics deals 2 damage to any target.\nWhen a spell or ability an opponent controls causes you to discard this card, it deals 4 damage to any target.",
    plain:"Two damage — and it punishes the opponent if they make you discard it."},
  "Tin Street Hooligan":{cost:"{1}{R}",type:"Creature — Goblin Rogue",pt:"2/1",frame:"R",
    text:"When this creature enters, if {G} was spent to cast it, destroy target artifact.",
    plain:"Pay for it with green mana and it smashes an artifact on the way in. Sideboarded in for the Jitte."},
  "Burning-Tree Shaman":{cost:"{1}{R}{G}",type:"Creature — Centaur Shaman",pt:"3/4",frame:"M",
    text:"Whenever a player activates an ability that isn't a mana ability, this creature deals 1 damage to that player.",
    plain:"Taxes the opponent every time they use an ability. Sideboarded out for this game."},
  "Kami of Ancient Law":{cost:"{1}{W}",type:"Creature — Spirit",pt:"2/2",frame:"W",
    text:"Sacrifice this creature: Destroy target enchantment.",plain:"A 2/2 that can eat an enchantment."},
  "Flames of the Blood Hand":{cost:"{2}{R}",type:"Instant",pt:"",frame:"R",
    text:"Flames of the Blood Hand deals 4 damage to target player or planeswalker. The damage can't be prevented. If that player or that planeswalker's controller would gain life this turn, that player gains no life instead.",
    plain:"Four damage to the face that can't be prevented, and it shuts off their lifegain."},
  "Umezawa's Jitte":{cost:"{2}",type:"Legendary Artifact — Equipment",pt:"",frame:"A",
    text:"Whenever equipped creature deals combat damage, put two charge counters on Umezawa's Jitte.\nRemove a charge counter from Umezawa's Jitte: Choose one —\n• Equipped creature gets +2/+2 until end of turn.\n• Target creature gets -1/-1 until end of turn.\n• You gain 2 life.\nEquip {2}",
    plain:"Attach it to a creature. Every time that creature connects, it stores two counters you can spend to pump, kill, or gain 2 life each. The most feared card of its era."},
  "Giant Solifuge":{cost:"{2}{R/G}{R/G}",type:"Creature — Insect",pt:"4/1",frame:"M",
    text:"Trample; haste; shroud",plain:"Attacks the turn it lands and can't be targeted."},
  "Hunted Wumpus":{cost:"{3}{G}",type:"Creature — Beast",pt:"6/6",frame:"G",
    text:"When this creature enters, each other player may put a creature card from their hand onto the battlefield.",
    plain:"A huge body, but it gives your opponent a free creature."},

  "Plagued Rusalka":{cost:"{B}",type:"Creature — Spirit",pt:"1/1",frame:"B",
    text:"{B}, Sacrifice a creature: Target creature gets -1/-1 until end of turn.",
    plain:"A 1/1 that converts any of your own creatures into a shrink-ray. It ends up deciding the middle of this game."},
  "Ravenous Rats":{cost:"{1}{B}",type:"Creature — Rat",pt:"1/1",frame:"B",
    text:"When this creature enters, target opponent discards a card.",
    plain:"A 1/1 that strips a card out of your opponent's hand."},
  "Dark Confidant":{cost:"{1}{B}",type:"Creature — Human Wizard",pt:"2/1",frame:"B",
    text:"At the beginning of your upkeep, reveal the top card of your library and put that card into your hand. You lose life equal to its mana value.",
    plain:"“Bob.” A free extra card every turn — paid for in life. At 7 life that bill gets dangerous."},
  "Hand of Cruelty":{cost:"{B}{B}",type:"Creature — Human Samurai",pt:"2/2",frame:"B",
    text:"Protection from white\nBushido 1 (Whenever this creature blocks or becomes blocked, it gets +1/+1 until end of turn.)",
    plain:"White creatures can't block it and can't damage it — and it grows when it fights. It is a wall Jones's white creatures simply cannot get past."},
  "Shrieking Grotesque":{cost:"{2}{W}",type:"Creature — Gargoyle",pt:"2/1",frame:"W",
    text:"Flying\nWhen this creature enters, if {B} was spent to cast it, target player discards a card.",
    plain:"A 2/1 flier that can strip a card."},
  "Paladin en-Vec":{cost:"{1}{W}{W}",type:"Creature — Human Knight",pt:"2/2",frame:"W",
    text:"First strike, protection from black and from red",
    plain:"Untouchable by red removal — a nightmare for a red deck."},
  "Teysa, Orzhov Scion":{cost:"{1}{W}{B}",type:"Legendary Creature — Human Advisor",pt:"2/3",frame:"M",
    text:"Sacrifice three white creatures: Exile target creature.\nWhenever another black creature you control dies, create a 1/1 white Spirit creature token with flying.",
    plain:"Turns dead black creatures into flying tokens."},
  "Ghost Council of Orzhova":{cost:"{W}{W}{B}{B}",type:"Legendary Creature — Spirit",pt:"4/4",frame:"M",
    text:"When Ghost Council of Orzhova enters, target opponent loses 1 life and you gain 1 life.\n{1}, Sacrifice a creature: Exile Ghost Council of Orzhova. Return it to the battlefield under its owner's control at the beginning of the next end step.",
    plain:"A 4/4 that blinks out of range of any removal spell. Ruel's best card — and it never shows up in this game."},
  "Okiba-Gang Shinobi":{cost:"{3}{B}{B}",type:"Creature — Rat Ninja",pt:"3/2",frame:"B",
    text:"Ninjutsu {3}{B}\nWhenever this creature deals combat damage to a player, that player discards two cards.",
    plain:"Empties your opponent's hand two cards at a time."},
  "Castigate":{cost:"{W}{B}",type:"Sorcery",pt:"",frame:"M",
    text:"Target opponent reveals their hand. You choose a nonland card from it and exile that card.",
    plain:"See their whole hand and delete the scariest card in it."},
  "Mortify":{cost:"{1}{W}{B}",type:"Instant",pt:"",frame:"M",
    text:"Destroy target creature or enchantment.",plain:"Kills any creature, at instant speed."},
  "Seize the Soul":{cost:"{2}{B}{B}",type:"Instant",pt:"",frame:"B",
    text:"Destroy target nonwhite, nonblack creature. Create a 1/1 white Spirit creature token with flying.\nHaunt (When this spell card is put into a graveyard after resolving, exile it haunting target creature.)\nWhen the creature this card haunts dies, destroy target nonwhite, nonblack creature. Create a 1/1 white Spirit creature token with flying.",
    plain:"Kills a red or green creature and leaves a flier behind — then does the whole thing a SECOND time later, whenever the creature it haunts dies."},
  "Orzhov Pontiff":{cost:"{1}{W}{B}",type:"Creature — Human Cleric",pt:"1/1",frame:"M",
    text:"Haunt\nWhen this creature enters or the creature it haunts dies, choose one —\n• Creatures you control get +1/+1 until end of turn.\n• Creatures you don't control get -1/-1 until end of turn.",
    plain:"Sweeps away a team of small creatures — twice."},
  "Descendant of Kiyomaro":{cost:"{1}{W}{W}",type:"Creature — Human Soldier",pt:"2/3",frame:"W",
    text:"As long as you have more cards in hand than each opponent, this creature gets +1/+2 and has \"Whenever this creature deals combat damage, you gain 3 life.\"",
    plain:"Grows and gains life while you are ahead on cards."},
  "Spirit":{cost:"",type:"Token Creature — Spirit",pt:"1/1",frame:"W",token:true,
    text:"Flying",plain:"A 1/1 flying token. Jones has nothing in his deck that can block it."},

  "Temple Garden":{taps:"GW",cost:"",type:"Land — Forest Plains",frame:"L",land:true,
    text:"({T}: Add {G} or {W}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    plain:"A “shock land”: pay 2 life to have it work immediately."},
  "Stomping Ground":{taps:"RG",cost:"",type:"Land — Mountain Forest",frame:"L",land:true,
    text:"({T}: Add {R} or {G}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    plain:"Red and green — and it counts as a Forest, which turns Kird Ape into a 2/3."},
  "Sacred Foundry":{taps:"RW",cost:"",type:"Land — Mountain Plains",frame:"L",land:true,
    text:"({T}: Add {R} or {W}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    plain:"Red and white, for 2 life — or free if you can afford to let it come in tapped."},
  "Battlefield Forge":{taps:"RW",cost:"",type:"Land",frame:"L",land:true,
    text:"{T}: Add {C}.\n{T}: Add {R} or {W}. This land deals 1 damage to you.",
    plain:"A “pain land”: coloured mana costs 1 life each time."},
  "Karplusan Forest":{taps:"RG",cost:"",type:"Land",frame:"L",land:true,
    text:"{T}: Add {C}.\n{T}: Add {R} or {G}. This land deals 1 damage to you.",plain:"Pain land, red or green."},
  "Brushland":{taps:"GW",cost:"",type:"Land",frame:"L",land:true,
    text:"{T}: Add {C}.\n{T}: Add {G} or {W}. This land deals 1 damage to you.",plain:"Pain land, green or white."},
  "Eiganjo Castle":{taps:"W",cost:"",type:"Legendary Land",frame:"L",land:true,
    text:"{T}: Add {W}.\n{W}, {T}: Prevent the next 2 damage that would be dealt to target legendary creature this turn.",
    plain:"White mana, with a small bonus for legendary creatures."},
  "Forest":{taps:"G",cost:"",type:"Basic Land — Forest",frame:"L",land:true,text:"{T}: Add {G}.",plain:"Taps for one green mana."},
  "Plains":{taps:"W",cost:"",type:"Basic Land — Plains",frame:"L",land:true,text:"{T}: Add {W}.",plain:"Taps for one white mana."},
  "Swamp":{taps:"B",cost:"",type:"Basic Land — Swamp",frame:"L",land:true,text:"{T}: Add {B}.",plain:"Taps for one black mana."},
  "Godless Shrine":{taps:"WB",cost:"",type:"Land — Plains Swamp",frame:"L",land:true,
    text:"({T}: Add {W} or {B}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    plain:"Shock land: white or black for 2 life."},
  "Caves of Koilos":{taps:"WB",cost:"",type:"Land",frame:"L",land:true,
    text:"{T}: Add {C}.\n{T}: Add {W} or {B}. This land deals 1 damage to you.",plain:"Pain land, white or black."},
  "Orzhov Basilica":{taps:"WB",cost:"",type:"Land",frame:"L",land:true,
    text:"This land enters tapped.\nWhen this land enters, return a land you control to its owner's hand.\n{T}: Add {W}{B}.",
    plain:"Two mana from one land — but it comes in tapped and bounces another land, so it costs you a whole turn."},
  "Shizo, Death's Storehouse":{taps:"B",cost:"",type:"Legendary Land",frame:"L",land:true,
    text:"{T}: Add {B}.\n{B}, {T}: Target legendary creature gains fear until end of turn.",plain:"Black mana, with an evasion trick."}
};

/* ── glossary ─────────────────────────────────────────────────── */
const GLOSS = {
  mana:["Mana","The game's currency. You tap lands to produce it, and you spend it to cast spells. Five colours: white, blue, black, red, green."],
  land:["Land","Your mana source. You may play one per turn, and that limit is the game's real clock — it's why a two-mana card is playable on turn two and a five-mana card isn't."],
  tap:["Tapping","Turning a card sideways to show it's been used. Lands tap for mana; creatures tap when they attack. Everything untaps at the start of your turn."],
  sick:["Summoning sickness","A creature can't attack on the turn it arrives. It has to survive a full round first."],
  mull:["Mulligan","Unhappy with your seven cards? Shuffle them back and draw seven again, then put one on the bottom. You start the game a card down — a real cost."],
  play:["On the play","Going first. You get the first land and the first threat, but you skip your first draw step. In a fast format that trade is usually worth it."],
  sb:["Sideboard","Fifteen extra cards. Between games of a match you may swap any of them into your 60, tuning the deck to the opponent you can now see."],
  burn:["Burn","Spells that just deal damage. They can go at a creature or straight at the opponent's face — which is what makes a burn deck able to win from a hopeless board."],
  pt:["Power / toughness","The two numbers on a creature. Power is how much damage it deals; toughness is how much it can take in one turn before dying. A 3/3 kills a 2/2 and survives."],
  block:["Blocking","The defending player chooses which of their untapped creatures intercept which attackers. Blocked damage hits the blocker instead of the player."],
  trade:["Trading","Both creatures die in combat. Usually fine — unless you paid more for yours than they did for theirs."],
  cardadv:["Card advantage","Ending up with more resources than your opponent. Every one-for-one trade is neutral; a card that kills two things, or draws you an extra card, puts you ahead."],
  tempo:["Tempo","Who is spending their turns doing what they want. An aggressive deck wins by making the opponent spend every turn reacting."],
  topdeck:["Topdeck","The card you draw for the turn, with nothing left in hand. “Topdecking” is playing off the top of your library, one card at a time."],
  prot:["Protection from white","A shield against everything white: it can't be blocked by white creatures, can't be damaged by them, and can't be targeted by white spells. Half of Jones's deck simply cannot interact with it."],
  bushido:["Bushido","Whenever this creature blocks or is blocked, it gets bigger for the turn. A 2/2 with bushido 1 fights as a 3/3."],
  haunt:["Haunt","When the spell finishes, it gets exiled “haunting” a creature. When that creature later dies, the spell's effect happens all over again — so it's two cards' worth of value out of one card."],
  radiance:["Radiance","Targets one creature, then hits every other creature sharing a colour with it. One Bathe in Light covers a whole white team."],
  equip:["Equipment","An artifact you attach to a creature for a cost. Equipping is slow — sorcery speed only — but the equipment survives when the creature dies."],
  shockland:["Shock land","A dual land that enters tapped unless you pay 2 life. Jones's deck runs eight; the life it costs him is real, and in this game it nearly matters."],
  painland:["Pain land","A dual land that charges 1 life every time you tap it for coloured mana."],
  token:["Token","A creature that isn't a card — created by a spell. It's a real creature in every other way."],
  upkeep:["Upkeep","The very start of your turn, before you draw. Cards like Dark Confidant collect their toll here."],
  instant:["Instant","A spell you can cast at any time, including during your opponent's turn. Sorceries can only be cast in your own main phase, on an empty board of pending actions."],
  eot:["End of turn","Casting an instant just before your opponent's turn ends. You get to see what they did first, and you still untap immediately afterwards — it's free information."],
  clock:["The clock","How many turns it takes you to kill the opponent. “A three-turn clock” means they have three draws to find an answer."],
  curve:["Curve","Playing a one-mana spell on turn one, a two-mana spell on turn two, and so on — using every point of mana every turn. Curving out is how an aggro deck wins."],
  aggro:["Aggro","A deck built to end the game quickly with cheap creatures and damage, before the opponent's more powerful cards matter."],
  removal:["Removal","A spell that kills a creature."],
  legend:["Legendary","You may only control one of a given legendary permanent at a time."],
  race:["Racing","Both players ignoring defence and attacking. The winner is whoever's clock is one turn faster — so every point of life, and every point of lifegain, is a turn."],
  stack:["The stack","Spells don't resolve instantly — they wait, and the opponent gets a chance to respond. Ruel used this to kill Jones's Kird Ape the moment it landed."]
};

/* ── decklists (official Top 8 lists) ─────────────────────────── */
const DECK_JONES = [["Creatures (22)",[[4,"Savannah Lions"],[4,"Isamaru, Hound of Konda"],[4,"Kird Ape"],[4,"Watchwolf"],[3,"Burning-Tree Shaman"],[3,"Kami of Ancient Law"]]],
  ["Spells (16)",[[2,"Bathe in Light"],[4,"Char"],[4,"Lightning Helix"],[3,"Flames of the Blood Hand"],[3,"Shock"]]],
  ["Lands (22)",[[4,"Sacred Foundry"],[4,"Battlefield Forge"],[4,"Stomping Ground"],[4,"Temple Garden"],[2,"Forest"],[1,"Eiganjo Castle"],[1,"Plains"],[1,"Karplusan Forest"],[1,"Brushland"]]],
  ["Sideboard (15)",[[1,"Flames of the Blood Hand"],[4,"Umezawa's Jitte"],[2,"Tin Street Hooligan"],[2,"Giant Solifuge"],[3,"Hunted Wumpus"],[3,"Guerrilla Tactics"]]]];
const DECK_RUEL = [["Creatures (28)",[[4,"Plagued Rusalka"],[4,"Ravenous Rats"],[4,"Dark Confidant"],[3,"Hand of Cruelty"],[2,"Shrieking Grotesque"],[2,"Paladin en-Vec"],[3,"Teysa, Orzhov Scion"],[4,"Ghost Council of Orzhova"],[2,"Okiba-Gang Shinobi"]]],
  ["Spells (10)",[[4,"Castigate"],[3,"Mortify"],[3,"Umezawa's Jitte"]]],
  ["Lands (22)",[[4,"Caves of Koilos"],[4,"Godless Shrine"],[4,"Orzhov Basilica"],[1,"Shizo, Death's Storehouse"],[1,"Eiganjo Castle"],[6,"Swamp"],[2,"Plains"]]],
  ["Sideboard (15)",[[2,"Terashi's Grasp"],[1,"Descendant of Kiyomaro"],[2,"Distress"],[2,"Cranial Extraction"],[2,"Phyrexian Arena"],[2,"Orzhov Pontiff"],[2,"Seize the Soul"],[2,"Slay"]]]];

/* ═══════════════════════════════════════════════════════════════
   THE REPLAY
   Each step mutates the board. `src` records where it comes from:
   coverage = official WotC event coverage
   report   = Craig Jones's own tournament report
   bridge   = reconstructed connective tissue (see the Sources sheet)
   ═══════════════════════════════════════════════════════════════ */
const STEPS = [

{turn:"The situation", src:"coverage", title:"Two players, one seat in the final",
 p:[`Honolulu, Sunday 5 March 2006. Eight players are left. <b>Craig Jones</b> is an English writer who has spent years covering the Pro Tour from the other side of the camera and has never made a Top 8 before. Across the table, <b>Olivier Ruel</b> is one of the best players in the world.`,
    `A match is best of five games. This one is <b>2&ndash;2</b>. The final, the trophy and &mdash; as it turns out &mdash; $16,000 all come down to game five.`],
 boxes:[{k:"rules",t:"If you've played one game of Magic, this is all you need",
   h:`Both players start at <b>20 life</b> and lose at 0. On your turn you untap everything, draw a card, put down at most one [[land]], spend [[mana|mana]] on spells, and attack with your creatures. Everything else in this game is those five things, done well.`}],
 do:h=>{}},

{turn:"The decks", src:"coverage", title:"Two decks that want opposite things",
 p:[`Jones is playing <b>Zoo</b>: twenty-two creatures, nearly all of them costing one or two mana, and sixteen spells that mostly just deal damage. It does not out-think you. It tries to be finished before you have started.`,
    `Ruel is playing <b>Hand in Hand</b>: twenty-eight creatures, discard, removal, and a card that draws him an extra card every turn. Every one of his cards trades with one of yours and leaves a little something behind.`,
    `So the game asks one question: can Jones deal twenty damage before Ruel's card quality takes the game away from him?`],
 boxes:[{k:"why",t:"The thing to watch",
   h:`Zoo's real weapon is not the creatures &mdash; it is the [[burn]]. Fourteen cards in Jones's deck can be pointed straight at Ruel's face. That means Jones can lose the board completely and still win, which is exactly what is about to happen.`},
  {k:"rules",t:"Press D",h:`Both full sixty-card lists are one keystroke away, any time.`}],
 do:h=>{}},

{turn:"Before the first card", src:"coverage", title:"On the play, and a mulligan",
 p:[`Jones lost game four, so he chooses to go first. Ruel does not like what he sees in his opening seven and takes a [[mull|mulligan]], keeping six.`,
    `Ruel had walked to the table with a warning about this exact situation.`],
 quote:{text:`So I was playtesting&hellip; Neither one of our decks won a game when we went second. I really hope I win this die roll.`,cite:"Olivier Ruel, before the match"},
 p2:[`He was right. Games one through four all went to the player who went first. Now it is game five, and Jones is [[play|on the play]].`],
 boxes:[{k:"rules",t:"Why going first is worth so much here",
   h:`Going first means your two-mana creature lands a full turn before theirs. The cost is that you skip your first draw. In a format this fast, that trade is almost always worth taking.`}],
 do:h=>{h.hand("jones",7); h.hand("ruel",6);}},

{turn:"Turn 1", src:"bridge", title:"A blank first turn",
 p:[`Jones plays a <b>Temple Garden</b> and pays 2 life to have it enter untapped &mdash; and then does nothing with it. For a deck whose entire plan is speed, a turn one with no creature is a bad start.`,
    `Ruel plays a <b>Godless Shrine</b>, also for 2 life, and casts <b>Plagued Rusalka</b>. It is a 1/1; it will never attack. It is not a threat, it is a tool, and by the end of the game it will have taken Jones's board apart.`],
 boxes:[{k:"rules",t:"Paying life for a land",
   h:`Both of those are [[shockland|shock lands]]: they arrive tapped and useless unless you pay 2 life. In a format where games end at 20 damage, that is a real price &mdash; and both players just paid it on turn one without blinking, because a turn is worth more than 2 life.`}],
 do:h=>{h.land("jones","Temple Garden"); h.life("jones",-2); h.hand("jones",-1);
        h.draw("ruel"); h.land("ruel","Godless Shrine"); h.life("ruel",-2); h.hand("ruel",-1);
        h.cast("ruel","Plagued Rusalka"); h.add("ruel","Plagued Rusalka"); h.hand("ruel",-1);
        h.note("Jones has the mana but nothing to spend it on.");}},

{turn:"Turn 2", src:"coverage", title:"Watchwolf, and a second Rusalka",
 p:[`Jones plays a Forest and casts <b>Watchwolf</b> &mdash; a 3/3 for two mana, which in 2006 was about as much raw size as two mana could buy.`,
    `Ruel plays a <b>Caves of Koilos</b>, takes 1 damage from it to make black mana, and adds his second <b>Plagued Rusalka</b>.`],
 boxes:[{k:"rules",t:"It can't attack yet",
   h:`A creature has [[sick|summoning sickness]]: it cannot attack the turn it arrives. The Watchwolf has to survive a full round first. This is why going first matters so much &mdash; Jones's clock starts a turn earlier than Ruel's.`}],
 do:h=>{h.draw("jones"); h.land("jones","Forest"); h.hand("jones",-1);
        h.cast("jones","Watchwolf"); h.add("jones","Watchwolf",{sick:true}); h.hand("jones",-1);
        h.draw("ruel"); h.land("ruel","Caves of Koilos"); h.hand("ruel",-1); h.life("ruel",-1);
        h.cast("ruel","Plagued Rusalka"); h.add("ruel","Plagued Rusalka"); h.hand("ruel",-1);}},

{turn:"Turn 3", src:"bridge", title:"Stuck on two lands — and it doesn't matter yet",
 p:[`Jones does not draw a third land. It hardly registers: he casts a <b>second Watchwolf</b> off the same two lands and sends the first one in. Ruel's Rusalkas are 1/1s he needs later, so he takes the hit. <b>17 &rarr; 14.</b>`,
    `Ruel, meanwhile, goes backwards. He plays an <b>Orzhov Basilica</b>, which enters tapped and forces him to return another land to his hand. It will pay him back later; right now it costs him a whole turn.`],
 boxes:[{k:"why",t:"This is the entire aggro plan",
   h:`Six power on the board on turn three, off two lands, while the opponent's mana goes <em>backwards</em>. Jones is not doing anything clever. He is just spending every point of mana every turn &mdash; [[curve|curving out]] &mdash; and that alone is enough to put a world-class player on the back foot.`}],
 do:h=>{h.draw("jones"); h.cast("jones","Watchwolf"); h.add("jones","Watchwolf",{sick:true}); h.hand("jones",-1);
        h.attackWith("jones",["Watchwolf"],1); h.life("ruel",-3);
        h.draw("ruel"); h.land("ruel","Orzhov Basilica",{tapped:true}); h.hand("ruel",-1); h.bounceLand("ruel","Caves of Koilos");
        h.note("One Watchwolf attacks for 3. Ruel declines to chump-block.");}},

{turn:"Turn 4", src:"coverage", title:"Bathe in Light: six damage out of nowhere",
 p:[`Still two lands. Instead of a creature, Jones spends them on <b>Bathe in Light</b> and names <b>black</b>. Both Watchwolves gain protection from black until end of turn &mdash; and every creature Ruel controls is black.`,
    `Nothing can block. Both Wolves connect. <b>14 &rarr; 8.</b>`],
 boxes:[{k:"rules",t:"Radiance",
   h:`Bathe in Light targets one creature and then hits <em>every other creature that shares a colour with it</em>. Watchwolf is green and white, so one card covers the whole team. That is the [[radiance]] mechanic, and it is why Jones runs a trick that does no damage of its own.`},
  {k:"why",t:"Making the best of a bad hand",
   h:`Jones is using his turn on a spell that leaves nothing behind, because at two lands the two-mana slot is the only slot he has. Six damage in a single turn, from a deck that is, on paper, stumbling.`}],
 do:h=>{h.draw("jones"); h.cast("jones","Bathe in Light"); h.hand("jones",-1);
        h.attackWith("jones",["Watchwolf","Watchwolf"],2); h.life("ruel",-6);
        h.note("Protection from black — Ruel's Rusalkas are not allowed to block.");}},

{turn:"Turn 4 · Ruel", src:"coverage", title:"A wall, and a look at the whole hand",
 p:[`Ruel plays a second <b>Godless Shrine</b>, pays 2 more life &mdash; he is down to <b>6</b> &mdash; and uses all four mana on two cards.`,
    `First, <b>Hand of Cruelty</b>. It is a 2/2, which sounds unremarkable until you read the first line: <em>protection from white</em>. Jones's Watchwolf is white. So is his Isamaru, and his Savannah Lions. None of them can block it, none of them can damage it, and it can block them all day.`,
    `Second, <b>Castigate</b>: Ruel looks at Jones's entire hand and takes the best card out of it. What he sees is <b>Tin Street Hooligan, Shock, Guerrilla Tactics, Isamaru</b> and <b>Kird Ape</b>. He exiles the <b>Shock</b>.`],
 boxes:[{k:"why",t:"Four of those five cards are red — and Jones has no red mana",
   h:`Jones is on a Forest and a Temple Garden. He is holding a hand full of red spells he physically cannot cast. Ruel can see all of it, and takes the cheapest burn spell because at 6 life the cheapest one is the one most likely to be cast in time.`},
  {k:"rules",t:"Protection from white",
   h:`[[prot|Protection]] is a hard shield, not a discount. It means <em>can't be blocked by, can't be damaged by, can't be targeted by</em> anything of that colour. It is about to cost Jones a 3/3 for free.`}],
 do:h=>{h.draw("ruel"); h.land("ruel","Godless Shrine"); h.life("ruel",-2); h.hand("ruel",-1);
        h.cast("ruel","Hand of Cruelty"); h.add("ruel","Hand of Cruelty",{sick:true}); h.hand("ruel",-1);
        h.cast("ruel","Castigate"); h.hand("ruel",-1);
        h.reveal(["Tin Street Hooligan","Shock","Guerrilla Tactics","Isamaru, Hound of Konda","Kird Ape"],"Shock");
        h.hand("jones",-1);
        h.note("Jones's hand is now public knowledge — and one card lighter.");}},

{turn:"Turn 5", src:"coverage", title:"The third land arrives, and Ruel falls to three",
 p:[`Jones draws <b>Stomping Ground</b>, pays 2 life, and finally has red mana.`,
    `He attacks with both Wolves. Ruel blocks one with the Hand of Cruelty: <b>bushido</b> makes it a 3/3 for the fight, and protection from white means the Watchwolf's damage is simply prevented. The Wolf dies having done nothing. The other Wolf gets through. <b>6 &rarr; 3.</b>`,
    `After combat, with the Hand back down to a 2/2, Jones burns it off the board with <b>Guerrilla Tactics</b>.`],
 boxes:[{k:"rules",t:"Bushido",
   h:`A creature with [[bushido]] gets bigger whenever it blocks or is blocked. So a 2/2 fights like a 3/3 &mdash; big enough to kill a Watchwolf &mdash; and shrinks straight back afterwards, small enough to die to a 2-damage burn spell.`},
  {k:"why",t:"Ruel is at 3 with a burn deck across the table",
   h:`Eight cards in Jones's remaining deck &mdash; four Char, four Lightning Helix &mdash; kill Ruel on the spot from here. He does not need a board, or a plan, or a turn. He needs one draw.`}],
 do:h=>{h.draw("jones"); h.land("jones","Stomping Ground"); h.life("jones",-2); h.hand("jones",-1);
        h.attackWith("jones",["Watchwolf","Watchwolf"],2);
        h.blockWith("ruel",["Hand of Cruelty"]);
        h.kill("jones","Watchwolf"); h.life("ruel",-3);
        h.cast("jones","Guerrilla Tactics"); h.hand("jones",-1); h.kill("ruel","Hand of Cruelty");
        h.note("A Wolf dies to the block; the other connects; the Hand is burned away after combat.");}},

{turn:"Turn 5 · Ruel", src:"bridge", title:"At three life, he needs a door that won't open",
 p:[`Ruel replays his <b>Caves of Koilos</b> and casts a <b>second Hand of Cruelty</b>.`,
    `Look at what that does to the board. Jones's surviving Watchwolf is green <em>and white</em>. It cannot block the Hand. The Hand can block it forever. Jones has a 3/3 that is, functionally, a spectator.`],
 boxes:[{k:"why",t:"Why 'just attack' stops working",
   h:`Aggro decks do not lose because the opponent gains life. They lose because at some point every attack becomes a bad attack. From here on, Jones's creatures are not a [[clock]] &mdash; they are decoration, and both players know it.`}],
 do:h=>{h.draw("ruel"); h.land("ruel","Caves of Koilos"); h.hand("ruel",-1);
        h.cast("ruel","Hand of Cruelty"); h.add("ruel","Hand of Cruelty",{sick:true}); h.hand("ruel",-1);}},

{turn:"Turn 6", src:"coverage", title:"Reinforcements, and four mana held open",
 p:[`Jones adds <b>Isamaru, Hound of Konda</b> &mdash; a 2/2 for one mana, and another white creature the Hand of Cruelty is immune to.`,
    `Ruel plays a Swamp and passes with every land untapped. A player on 3 life against a burn deck does not leave mana up for nothing. He is holding an [[instant]].`],
 boxes:[{k:"rules",t:"Instants are why you leave mana open",
   h:`Sorceries and creatures can only be cast in your own turn. [[instant|Instants]] can be cast at any moment, including in the middle of your opponent's turn. Ruel is waiting to see what Jones commits before he spends anything.`}],
 do:h=>{h.draw("jones"); h.land("jones","Plains"); h.hand("jones",-1);
        h.cast("jones","Isamaru, Hound of Konda"); h.add("jones","Isamaru, Hound of Konda",{sick:true}); h.hand("jones",-1);
        h.draw("ruel"); h.land("ruel","Swamp"); h.hand("ruel",-1);
        h.note("Ruel passes with everything untapped. Something is coming.");}},

{turn:"Turn 7", src:"coverage", title:"Kird Ape walks into Seize the Soul",
 p:[`Jones casts <b>Kird Ape</b>. Because Stomping Ground counts as a Forest, the Ape is a 2/3 for one mana &mdash; and, crucially, it is <em>red</em>, so it can block the Hand of Cruelty.`,
    `Ruel responds immediately with <b>Seize the Soul</b>. The Ape dies before it has done anything, Ruel gets a <b>1/1 flying Spirit</b> out of the deal, and the card itself is exiled <em>haunting</em> a creature &mdash; which means it is going to do all of that a second time, later, for free.`],
 quote:{text:`I don't think the Ape was a mistake. Yes, he could gun it down at will with Seize the Soul&hellip; but he could do that anyway, to any Red creature I cast.`,cite:"Craig Jones, tournament report"},
 boxes:[{k:"rules",t:"Haunt",
   h:`[[haunt|Haunt]] is the strangest thing on this board. When the spell finishes resolving it does not go to the graveyard &mdash; it gets exiled attached to a creature. When <em>that</em> creature dies, the whole spell happens again. Ruel gets two cards' worth out of one.`},
  {k:"bridge",t:"One inferred detail",
   h:`The coverage does not record which creature Ruel chose to haunt. The only reading that fits what happens five turns from now is that he hung it on <em>one of his own Plagued Rusalkas</em> &mdash; a creature he can sacrifice whenever he likes, which turns the haunt from a hope into a button.`}],
 do:h=>{h.draw("jones"); h.land("jones","Eiganjo Castle"); h.hand("jones",-1);
        h.cast("jones","Kird Ape"); h.hand("jones",-1); h.add("jones","Kird Ape",{sick:true,pt:"2/3"});
        h.cast("ruel","Seize the Soul","in response"); h.hand("ruel",-1);
        h.kill("jones","Kird Ape");
        h.add("ruel","Spirit",{sick:true});
        h.haunt("ruel","Plagued Rusalka");
        h.note("The Ape never gets to block. Ruel gains a flier and banks half a card.");}},

{turn:"Turn 7 · Ruel", src:"coverage", title:"He draws Umezawa's Jitte. Now: what would you do?",
 p:[`Ruel is on <b>3 life</b>. Jones is on 16. Ruel's board is two Plagued Rusalkas, a Hand of Cruelty and a 1/1 flying token. And he has just drawn the most feared card of the era.`,
    `<b>Umezawa's Jitte</b> is an [[equip|equipment]]. Attach it to a creature; every time that creature connects, it banks two counters, and each counter can be spent to pump a creature, shrink one of theirs, or <b>gain 2 life</b>.`,
    `But Ruel also knows &mdash; because Castigate showed him &mdash; that Jones is still holding a <b>Tin Street Hooligan</b>, a creature that destroys an artifact the moment it lands.`],
 boxes:[{k:"puzzle",t:"The coverage stopped here and asked the room",
   h:`<em>“With Jones controlling only two white creatures, but also knowing he holds a Hooligan in hand, do you cast the Jitte or not? If you cast the Jitte, which creature do you equip it to &mdash; the token or the Hand?”</em><br><br>Take a second before you press &rarr;.`}],
 do:h=>{h.draw("ruel"); h.note("Ruel: 3 life. Jones: 16 life, and a Hooligan he has already been forced to show.");}},

{turn:"Turn 7 · Ruel", src:"coverage", title:"He casts it — and never intends to keep it",
 p:[`Ruel casts the Jitte, equips it to the <b>flying token</b>, and attacks for exactly 1 in the air. Jones has nothing that can block a flier. <b>16 &rarr; 15.</b>`,
    `The Jitte banks two counters. Ruel spends both of them immediately, not on the board, but on <b>life</b>: <b>3 &rarr; 7</b>.`,
    `Then, before ending his turn, he moves the Jitte across to the Hand of Cruelty.`],
 math:`Spirit connects&nbsp;&nbsp;&nbsp; <b>+2 charge counters</b>\nspend a counter &rarr; gain 2&nbsp;&nbsp;&nbsp; Ruel <b>3 &rarr; 5</b>\nspend a counter &rarr; gain 2&nbsp;&nbsp;&nbsp; Ruel <b><span class="hit">5 &rarr; 7</span></b>`,
 boxes:[{k:"why",t:"This is the play of the game, and it has nothing to do with the board",
   h:`At 3 life, a single Char or Lightning Helix off the top killed Ruel. At <b>7</b>, it doesn't. Those four points of life did not save him from a creature &mdash; they turned “Jones needs one burn spell” into “Jones needs <b>two</b>”, which is a completely different game.`},
  {k:"rules",t:"And why move the Jitte afterwards?",
   h:`The Hooligan will kill the Jitte wherever it sits, so moving it is free. But if the Hooligan never shows up, a Jitte on the unblockable Hand of Cruelty ends the game in about three swings. Ruel is taking the version of the future that costs nothing.`}],
 do:h=>{h.cast("ruel","Umezawa's Jitte"); h.hand("ruel",-1);
        h.add("ruel","Umezawa's Jitte",{art:true});
        h.equip("ruel","Umezawa's Jitte","Spirit");
        h.attackWith("ruel",["Spirit"],1); h.life("jones",-1);
        h.life("ruel",4);
        h.equip("ruel","Umezawa's Jitte","Hand of Cruelty");
        h.note("Two counters, spent straight on life. 15 – 7.");}},

{turn:"Turn 8", src:"coverage", title:"The Hooligan does its job — and it isn't enough",
 p:[`Jones casts <b>Tin Street Hooligan</b>, deliberately paying for it with <b>green</b> mana so its ability turns on, and the Jitte is destroyed.`,
    `That is exactly why he put two of them in his sideboard. But count what actually happened. Ruel spent one card and got four life and a permanent change in the maths. Jones spent a card answering it and got a 2/1 that cannot attack into anything.`],
 quote:{text:`Once the early rush is over, you don't really care about the board. It's just a case of hanging on until the burn arrives.`,cite:"Craig Jones, tournament report"},
 boxes:[{k:"why",t:"Answering a card is not the same as beating it",
   h:`This is one of the hardest things to feel as a new player. Jones “dealt with” the Jitte. He also fell four points further from winning, spent his turn, and handed Ruel the whole board. [[cardadv|Card advantage]] is a real thing, but it is not the only currency.`}],
 do:h=>{h.draw("jones"); h.cast("jones","Tin Street Hooligan"); h.hand("jones",-1);
        h.add("jones","Tin Street Hooligan",{sick:true}); h.kill("ruel","Umezawa's Jitte");
        h.note("Paid with green mana, so the artifact-destruction trigger turns on.");}},

{turn:"Turn 8 · Ruel", src:"coverage", title:"“A little fist pump”",
 p:[`Ruel draws <b>Dark Confidant</b> &mdash; “Bob” &mdash; and casts it, with another <b>Plagued Rusalka</b> behind it.`,
    `Dark Confidant hands you a free extra card at the start of every one of your turns, and charges you life for it equal to that card's cost. Ruel's deck is full of four- and five-mana cards. He is on 7 life against a burn deck.`],
 boxes:[{k:"rules",t:"The upkeep",
   h:`Bob collects at the very start of your turn, in the [[upkeep]], before you draw normally. You do not get to decline. Casting it at 7 life against Zoo is a genuine gamble &mdash; Ruel is betting he can bury Jones in cards before Jones finds two burn spells.`},
  {k:"why",t:"Remember this card",
   h:`It is about to die before it ever triggers, and that is one of the two or three reasons this game ends the way it does.`}],
 do:h=>{h.draw("ruel"); h.cast("ruel","Dark Confidant"); h.hand("ruel",-1);
        h.add("ruel","Dark Confidant",{sick:true});
        h.cast("ruel","Plagued Rusalka"); h.add("ruel","Plagued Rusalka",{sick:true}); h.hand("ruel",-1);}},

{turn:"Turn 9", src:"coverage", title:"A trade Jones didn't need to make",
 p:[`Jones sends <b>Isamaru</b> in. Ruel blocks with <b>Dark Confidant</b> and the two trade &mdash; a 2/2 and a 2/1 kill each other.`,
    `Then Ruel sacrifices one Plagued Rusalka to another, shrinking the <b>Tin Street Hooligan</b> to 1/0. It dies too. Two of Jones's three creatures are gone, and Jones is back to a lone Watchwolf.`],
 quote:{text:`Sending in the lone Isamaru wasn't the best. I did have a second one in hand, but I'm fairly sure Olivier was going to throw Bob Confidant at the Hooligan at end of turn in any case.`,cite:"Craig Jones, tournament report"},
 boxes:[{k:"why",t:"But look what it bought him, by accident",
   h:`Dark Confidant died on <em>Jones's</em> turn &mdash; before Ruel's next upkeep. It never triggered once, so it never cost Ruel a single point of life. Ruel stays on exactly <b>7</b>, and 7 is the number this entire game turns on.`}],
 do:h=>{h.draw("jones"); h.land("jones","Sacred Foundry",{tapped:true}); h.hand("jones",-1);
        h.attackWith("jones",["Isamaru, Hound of Konda"],1);
        h.blockWith("ruel",["Dark Confidant"]);
        h.kill("jones","Isamaru, Hound of Konda"); h.kill("ruel","Dark Confidant");
        h.kill("ruel","Plagued Rusalka"); h.kill("jones","Tin Street Hooligan");
        h.note("Isamaru trades with Bob; a Rusalka is sacrificed to shrink the Hooligan to death.");}},

{turn:"Turn 9 · Ruel", src:"coverage", title:"Now the clock points the other way",
 p:[`Ruel attacks with the <b>Hand of Cruelty</b> and the <b>Spirit token</b>. Jones's Watchwolf is white, so it may not block the Hand. The Spirit has flying, so it may not block that either.`,
    `Three damage, unstoppably, every turn from here. <b>15 &rarr; 12.</b>`],
 boxes:[{k:"why",t:"Five turns to live",
   h:`Jones is now the one on a [[clock]]. At three a turn, he has five draws left before he is dead &mdash; and the only cards that matter in those five draws are the ones that deal damage to Ruel's face.`}],
 do:h=>{h.draw("ruel"); h.land("ruel","Swamp"); h.hand("ruel",-1);
        h.attackWith("ruel",["Hand of Cruelty","Spirit"],2); h.life("jones",-3);
        h.note("Nothing Jones controls is legally allowed to block either attacker.");}},

{turn:"Turn 10", src:"coverage", title:"More creatures that can't do anything",
 p:[`Jones casts a <b>second Isamaru</b> and a <b>second Kird Ape</b>. It looks like a board coming back together.`,
    `It isn't. The Isamaru is white and cannot get past the Hand of Cruelty. The Ape is a 2/3 that dies to any of Ruel's tricks. Neither can block a flier. Ruel adds <b>Ravenous Rats</b> &mdash; whose discard trigger finds nothing, because Jones's hand is already empty &mdash; and attacks again. <b>12 &rarr; 9.</b>`],
 boxes:[{k:"why",t:"A board is not the same as a threat",
   h:`Three creatures, seven power, and not a single point of it can be delivered. Learning to see the difference between “I have creatures” and “I have a way to win” is most of what separates a new player from an experienced one.`}],
 do:h=>{h.draw("jones");
        h.cast("jones","Isamaru, Hound of Konda"); h.add("jones","Isamaru, Hound of Konda",{sick:true}); h.hand("jones",-1);
        h.cast("jones","Kird Ape"); h.add("jones","Kird Ape",{sick:true,pt:"2/3"}); h.hand("jones",-1);
        h.draw("ruel"); h.cast("ruel","Ravenous Rats"); h.add("ruel","Ravenous Rats",{sick:true}); h.hand("ruel",-1);
        h.attackWith("ruel",["Hand of Cruelty","Spirit"],2); h.life("jones",-3);}},

{turn:"Turn 11", src:"report", title:"The attack Jones didn't make",
 p:[`Jones draws a land. He looks at three creatures that cannot profitably attack, and passes the turn. Ruel swings again: <b>9 &rarr; 6.</b>`,
    `Watching the coverage back afterwards, Jones named this &mdash; not the Kird Ape, not the Isamaru &mdash; as his real mistake.`],
 quote:{text:`The really big mistake was not attacking to clear the Rusalkas. It would have been a very bad attack for me as I'd have lost everything for no damage, but I would have at least cleared the Rusalkas off the board.`,cite:"Craig Jones, tournament report"},
 boxes:[{k:"mistake",t:"Why a terrible-looking attack was the right one",
   h:`Each Plagued Rusalka is a creature that converts <em>another</em> creature into a &minus;1/&minus;1 effect, at instant speed, for one mana. They are the reason Ruel can dismantle Jones's board whenever he chooses. Attacking would have cost Jones three creatures for zero damage &mdash; three creatures he was never going to attack with anyway &mdash; and taken Ruel's best tool away with them.`},
  {k:"why",t:"The general lesson",
   h:`A play that loses you material can still be correct, if what it removes is the opponent's <em>ability to act</em>. Count what a card does, not what it costs.`}],
 do:h=>{h.draw("jones"); h.land("jones","Forest"); h.hand("jones",-1);
        h.draw("ruel"); h.land("ruel","Plains"); h.hand("ruel",-1);
        h.attackWith("ruel",["Hand of Cruelty","Spirit"],2); h.life("jones",-3);
        h.note("No attack from Jones. The Rusalkas survive — and they will be used.");}},

{turn:"Turn 12", src:"report", title:"Char arrives too late, and the board comes apart",
 p:[`Jones draws <b>Char</b>. His first burn spell in a very long time &mdash; and it deals 4, when Ruel is on 7. It does not kill. He holds it.`,
    `Then, at the end of Jones's turn, Ruel cashes in everything at once. He sacrifices the haunted Plagued Rusalka to his other Rusalka, shrinking Isamaru. The Rusalka dying sets off the <b>haunt from Seize the Soul</b> &mdash; the card he cast five turns ago &mdash; which destroys the Kird Ape and makes a <b>second flying Spirit</b>. That new token is immediately sacrificed to shrink Isamaru again, and it dies.`,
    `Jones is left with one Watchwolf and one card in hand.`],
 quote:{text:`Then a Char showed up. It felt way too late. I was on six life, and there was no way I could attack through. Olivier decimated most of my board at end of turn.`,cite:"Craig Jones, tournament report"},
 boxes:[{k:"rules",t:"That's what haunt was for",
   h:`Seize the Soul killed a creature on turn seven. On turn twelve it kills another one and makes another token, because the creature it was haunting finally died &mdash; and Ruel chose that creature precisely so he could kill it whenever it suited him.`},
  {k:"bridge",t:"Reconstructed detail",
   h:`Both sources agree on the outcome &mdash; “the haunt from Seize the Soul plus Rusalka tricks left Jones with only a Watchwolf in play” &mdash; but neither records the exact order of the sacrifices. This is the sequence that produces it.`}],
 do:h=>{h.draw("jones");
        h.kill("ruel","Plagued Rusalka",{haunted:true}); h.kill("jones","Kird Ape"); h.kill("jones","Isamaru, Hound of Konda");
        h.note("End of turn: one sacrifice, one haunt trigger, one board wiped.");}},

{turn:"Turn 12 · Ruel", src:"report", title:"The safe attack that threw the match away",
 p:[`Ruel attacks with only the <b>Spirit</b> and the <b>Hand of Cruelty</b>, holding the Rusalka and the Ravenous Rats back as blockers. Jones: <b>6 &rarr; 3.</b>`,
    `It looks like sound, careful play from a world-class player who is a turn from the final. It is the losing move, and here is the arithmetic.`],
 math:`<b>WHAT HE DID</b>\nHand 2 + Spirit 1&nbsp;&nbsp;&nbsp; Jones <b>6 &rarr; 3</b>\nChar hits Jones for 2&nbsp;&nbsp;&nbsp; Jones <b>3 &rarr; 1</b> &nbsp;alive\n\n<b>IF HE HAD SENT EVERYTHING</b>\n2 + 1 + Rusalka 1 + Rats 1 = 5\nWatchwolf blocks one 1/1&nbsp;&nbsp;&nbsp; Jones <b>6 &rarr; 2</b>\nChar hits Jones for 2&nbsp;&nbsp;&nbsp; Jones <b><span class="hit">2 &rarr; 0</span></b> &nbsp;dead\nJones dies casting his own spell.`,
 quote:{text:`Olivier decimated most of my board at end of turn, and then fortunately attacked with only the Spirit and Hand.`,cite:"Craig Jones, tournament report"},
 boxes:[{k:"why",t:"Blockers only protect you from attacks",
   h:`Jones had one creature and it could not attack. Nothing Ruel held back was ever going to block anything. The only thing that could kill him was a card in Jones's hand, and keeping two 1/1s at home did precisely nothing about that &mdash; while costing him the two points that would have made Char unusable.`}],
 do:h=>{h.draw("ruel");
        h.attackWith("ruel",["Hand of Cruelty","Spirit"],2); h.life("jones",-3);
        h.note("Rusalka and Rats stay home. Those two points of damage are the match.");}},

{turn:"End of turn", src:"report", title:"Char, at the face",
 p:[`With Ruel's turn ending, Jones spends his last card. <b>Char</b>, pointed at Ruel's head: 4 damage to Ruel, 2 damage to himself.`,
    `<b>Ruel 7 &rarr; 3. Jones 3 &rarr; 1.</b> Empty hand, one Watchwolf, and Ruel kills him next turn from any direction.`],
 quote:{text:`Sorry, but there is no way I ever even consider Charring the Hand. I can't ever win the fight for board position at this stage in the game. My only outs are to go to the head and pray.`,cite:"Craig Jones, tournament report"},
 boxes:[{k:"rules",t:"Why cast it now and not on his own turn?",
   h:`Casting an instant at the [[eot|end of the opponent's turn]] is free: you see everything they did first, and you untap immediately afterwards with all your mana still available. There is essentially never a reason to do it earlier.`},
  {k:"why",t:"What he needs from one card",
   h:`Ruel is on 3. Jones has one draw. <b>Shock</b> deals 2 &mdash; not enough. <b>Guerrilla Tactics</b> deals 2 &mdash; not enough. Only <b>Char</b> (4) and <b>Lightning Helix</b> (3) do it. Three Chars and four Helixes are left in a library of forty-two.<br><br><b>Seven outs. About one in six.</b>`}],
 do:h=>{h.cast("jones","Char","end of turn"); h.hand("jones",-1);
        h.life("ruel",-4); h.life("jones",-2);
        h.note("Jones: 1 life, no cards in hand. Ruel: 3 life, and lethal on board.");}},

{turn:"Turn 13", src:"coverage", climax:true, title:"“Slam it!”",
 hero:"Lightning Helix", heroKicker:"Drawn off the top",
 heroTitle:"Exactly three damage, for exactly the win",
 heroSub:"Seven cards in his library could do it. This was one of them.",
 p:[`Ruel stood up from the table and started pacing. Then he told his opponent not to look.`,
    `Jones put his hand on his library, turned the card over without reading it, and put it on the table face up.`],
 klaxon:{t:"Lightning Helix",
   h:`<b>Three damage to any target, and you gain three life.</b><br><br>Ruel: <b>3 &rarr; 0.</b> Craig Jones is in the final.`},
 quote:{text:`It was a Lightning Helix. For a moment, it didn't register. I mean, I hadn't seen one of the goddamn things the whole match. I'd almost forgotten they were in my deck. That's a Lightning Helix. It's a Lightning Helix. Ohmigod I'm in the final.`,cite:"Craig Jones, tournament report"},
 do:h=>{h.draw("jones"); h.cast("jones","Lightning Helix"); h.hand("jones",-1);
        h.life("ruel",-3); h.life("jones",3);
        h.note("One in six.");}},

{turn:"Afterwards", src:"report", title:"What a beginner should take away from this",
 p:[`Jones lost the final to Mark Herberholz and the two of them split the prize money down the middle, which is how one card off the top of a library came to be worth <b>$16,000</b>. Twenty years on it is still the most famous single draw in the game's history.`,
    `Five things in this game are worth more than the ending:`],
 boxes:[
  {k:"why",t:"1 · Life is a resource, not a score",
   h:`Ruel paid 2 life for a land twice. Jones paid 2 twice more. And the four life a Jitte gained is what turned “Jones needs one burn spell” into “Jones needs two”. Nobody in this game treated 20 as a number to protect &mdash; they spent it, deliberately, and the spending decided it.`},
  {k:"why",t:"2 · A lost board is not a lost game",
   h:`From turn nine onward Jones could not attack, could not block, and could not win a fight. He won anyway, because fourteen cards in his deck do not care what is on the table.`},
  {k:"why",t:"3 · Attacking is not only about damage",
   h:`Jones's own biggest regret is an attack that would have dealt zero damage and cost him three creatures &mdash; because it would have stripped Ruel of the tool he used to take the game.`},
  {k:"why",t:"4 · Defence only defends against offence",
   h:`Ruel held two 1/1s back against an opponent whose only remaining weapon was a card in hand. Ask what the opponent can actually do to you, then defend against <em>that</em>.`},
  {k:"why",t:"5 · Colours are rules, not flavour",
   h:`A 3/3 Watchwolf lost a fight to a 2/2 and then spent the rest of the game unable to block it, because of three words on a card: <em>protection from white</em>. Read the small print on the board before you plan around it.`}],
 quote:{text:`Okay, so you could argue I was probably due it&hellip; While valid, those arguments take away from the magic of the moment. I don't think there has ever been a more dramatic finish to a top 8 match in the history of the Pro Tour.`,cite:"Craig Jones, tournament report"},
 do:h=>{}}

];
