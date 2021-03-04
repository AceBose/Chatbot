import nltk
nltk.download('punkt')
from irc_socket import *
import random
import time
from statemachine import StateMachine, State
import sys




initial_outreaches = ["Hi", "Hello", "Hey there", "Howdy", "Yoooo", "Yo", "Hey", "Welcome"]
secondary_outreaches = ["Hello???", "Anyone there???", "Hiii", "Hellooo", "I said hi", "excuse me???"]
frustrated_phrases = ["Screw you!", "Well, bye then", "Whatever, fine. Don't answer", "Ugh ok, bye",
                      "Forget youuuuuu (in CeeLo Green voice)", "I'm leaving..."]
confused_phrases = ["I don't understand", "Can you say that again?", "Nani?!?", "What did you say?",
                    "Literally idk dude", "Bro, what???", "Huh???"]

# when chatbot is speaker one
pairs_outreach = {"intro": ["What's up?", "How's it going", "What's happening?"]}

# when chatbot is speaker two
pairs_response = {
    "intro": ["Hello", "Hey there", "Howdy", "Yoooo", "Hey", "Welcome"],
    "inquiry": [("I'm good", "How are you?"), ("I'm fine, thanks", "And you?"),
                ("Nothing much", "You?"), ("Great", "What about you?")]
}

get_next_outreach = lambda utterance: random.choice(pairs_outreach[utterance])
get_next_response = lambda utterance: random.choice(pairs_response[utterance])

# travel rec stuff
import travelRecs as trav
travel_time_questions = ["When are you leaving?",
                         "When would you like to travel?",
                         "What time are you thinking of going?",
                         "When are you free to fly?"]

travel_temp_questions = ["How hot do you like it?",
                         "What temperature are you looking for?",
                         "What's the weather you're looking for?"]

travel_guess = ["OK, I'll take a guess then.",
                "Well that isn't helpful, but I can take a shot in the dark.",
                "Alright, let me choose some of my favorites."]

travel_recs = ["I've heard {place} is great in {month}!",
               "If you're traveling in {month}, head to {place}!",
               "When {month} comes around, visit {place}!",
               "I'd recommend {place}, during the month of {month}."]

temp_words = {
    "hot": 85, "cold": 50, "warm": 75, "cool": 65, "chilly": 55, "toasty": 85,
}


def main():
    # python3 testbot.py irc.freenode.net “#CPE482” myNickname
    if len(sys.argv) == 4:
        server = sys.argv[1]
        channel = sys.argv[2].strip("\"")
        botnick = sys.argv[3]
        bot = ChatBot(server=server, channel=channel, botnick=botnick)
    else:
        bot = ChatBot()

    bot.init_bot()
    bot.run_bot()


# state keeps track of where in the discourse we are
class ChatState(StateMachine):
    start = State('START', initial=True)
    initial_outreach = State('INITIAL_OUTREACH')
    secondary_outreach = State('SECONDARY_OUTREACH')
    outreach_reply = State('OUTREACH_REPLY')
    inquiry = State('INQUIRY')
    # this is a super state that encapsulates inquiry reply and inquiry of speaker two
    inquiry_super = State('INQUIRY_SUPER')
    inquiry_reply = State('INQUIRY_REPLY')
    giveup_frustrated = State('GIVEUP_FRUSTRATED')
    end = State('END')

    reach_out = start.to(initial_outreach)
    response = initial_outreach.to(outreach_reply) | start.to(outreach_reply)
    no_reply_one = initial_outreach.to(secondary_outreach)
    no_reply_after_second = secondary_outreach.to(giveup_frustrated)
    retry_secondary = secondary_outreach.to(secondary_outreach)
    second_response = secondary_outreach.to(outreach_reply)
    retry_outreach = outreach_reply.to(outreach_reply)
    no_inquiry = outreach_reply.to(giveup_frustrated)
    inquiry_given = outreach_reply.to(inquiry)
    inquiry_response = inquiry.to(inquiry_super)
    retry_inquiry = inquiry.to(inquiry)
    to_next_inquiry = inquiry_super.to(inquiry_reply)
    ignore_after_inquiry = inquiry.to(giveup_frustrated)
    ignore_after_inquiry_two = inquiry_super.to(giveup_frustrated)
    happy_end = inquiry_reply.to(end)
    giveup_end = giveup_frustrated.to(end)
    restart = start.from_(start, initial_outreach, secondary_outreach, outreach_reply, inquiry,
                          inquiry_reply, inquiry_super, giveup_frustrated, end)


class ChatBot:  # init here
    def __init__(self, server="irc.freenode.net", channel="#CSC482", botnick="Default-bot"):
        self.bot_state = ChatState()
        self.bot_response = ""
        self.awaiting_response = False
        self.users = []
        self.target = ""
        self.server = server
        self.channel = channel
        self.botnick = botnick if "-bot" in botnick[-4:] else botnick + "-bot"
        self.irc = IRCSocket()
        self.irc.connect(server, channel, self.botnick)
        self.user_text = ""
        self.retries = 0
        self.spoke_first = None
        self.sent_forget = False
        self.seconds_passed = 0
        self.travel_month = ""
        self.travel_temp = 0
        self.travel_df = None

    def init_bot(self):
        while True:
            text = self.irc.get_response()
            if "JOIN" in text:
                break
        time.sleep(1)
        self.get_names()

    def get_names(self):
        names = self.irc.get_names(self.channel)
        names_no_bot = [name for name in names if self.botnick not in name]
        self.users = names_no_bot

    def check_msg(self, _text):
        return "PRIVMSG" in _text and self.channel in _text and self.botnick + ":" in _text

    def get_user_text(self, _text):
        exp_index = _text.find("!")
        who_sent = _text[1:exp_index] if exp_index > 0 else ""

        self.check_for_commands()
        if not self.target or (self.bot_state.is_secondary_outreach and self.seconds_passed > 10):
            self.target = who_sent

        name_index = _text.find(self.botnick)
        self.user_text = _text[name_index + len(self.botnick) + 1:].strip().lower()  # +1 to get rid of colon

        print(f"{who_sent} said `{self.user_text}`")
        self.check_for_commands()
        if who_sent != self.target:
            return False
        return True

    def check_for_commands(self):
        if "die" == self.user_text:
            self.irc.kill_self(self.channel)
            exit()
        elif "forget" == self.user_text:
            self.sent_forget = True
            self.bot_state.restart()

    def wait_for_text(self, no_message_func, has_message_func):
        text = self.get_timed_response()  # first 30 seconds
        if self.sent_forget:
            self.sent_forget = False
            self.awaiting_response = True  # treat like no response in pipeline
            return False
        if text:
            self.awaiting_response = False
            has_message_func()
        else:
            self.awaiting_response = True
            no_message_func()
        return self.awaiting_response

    def get_timed_response(self):
        self.seconds_passed = 0
        text = None
        while self.seconds_passed != 30 and not self.sent_forget:
            if self.seconds_passed % 5 == 0:
                print(f"{self.seconds_passed} tries")
            text = self.get_response()
            if text:
                return text
            self.seconds_passed += 1
        return text

    def get_response(self):
        text = None
        if self.irc.poll_read_response():
            text = self.irc.get_response()
            if text:
                for line in text.split("\n"):
                    if self.check_msg(line) and self.get_user_text(line):
                        return line
                text = None
        return text

    def send_question_answer_pair(self, resp, send_question=True):
        if isinstance(resp, tuple):
            answer = resp[0]
            question = resp[1]  # question
            self.irc.send_dm(self.channel, self.target, answer)
            if send_question:
                self.irc.send_dm(self.channel, self.target, question)

    @staticmethod
    def remove_conjunctions(_text):
        conjunctions = {"'s": "is", "'re": "are", "'t": "not", "'d": "did"}
        tokenized_text = nltk.word_tokenize(_text)
        for i in range(len(tokenized_text)):
            if tokenized_text[i] in conjunctions.keys():
                tokenized_text[i] = conjunctions[tokenized_text[i]]
        return ' '.join(tokenized_text)

    @staticmethod
    def normalize_response(_text):
        intro_words = ["hey", "hello", "hi", "yo", "welcome", "howdy"]
        one_word_inquiry = ["you?"]
        inquiry_start = ["how", "what", "and"]
        inquiry_next = ["you", "going", "happening", "good", "popping", "cracking", "everything", "things", "life", "up"]
        slang_phrases = ["wassup", "sup", "wazzup", "poppin", "crackin", "whaddup", "it do"]
        if _text.lower() == one_word_inquiry:
            return "inquiry"
        processed_text = ChatBot.remove_conjunctions(_text).lower()
        for start in inquiry_start:
            for nxt in inquiry_next:
                if start and nxt in processed_text:
                    return "inquiry"
        for slang in slang_phrases:
            if slang in processed_text:
                return "inquiry"
        for word in intro_words:
            if word in processed_text:
                return "intro"
        return "unknown"

    def check_unique_question_hari(self, _text):
        # asks top X artists -> ask for genre -> user gives genre -> bot sends top 10 songs for genre
        # -> user asks if artist in top 10 -> bot says yes or no and prints song
        return False

    def check_unique_question_clay(self, _text):
        # asks travel recommendation -> bot asks when you want to visit -> user gives time -> bot asks what temperature
        # -> users sends temperature -> bot sends final recommendation
        travel_words = ["travel", "go", "fly", 'explore', "visit"]
        question_start = ["where", "what"]
        processed_text = ChatBot.remove_conjunctions(_text).lower()
        for start in question_start:
            for nxt in travel_words:
                if start and nxt in processed_text:
                    return True

        return False

    def check_unique_question_archit(self, _text):
        # asks recipe or ingredients in food -> bot gives recipe -> user asked for ingredients
        # -> bot returns ingredients
        return False

    def recommend_travel(self, _text):
        if not self.travel_df:
            # this takes a bit maybe warn user?
            # self.irc.send_dm(self.channel, self.target, 'Let me think a bit.')
            self.travel_df = trav.get_travel_df()

        self.get_travel_time(_text)
        self.get_travel_temp(_text)

        if not self.travel_month:
            self.prompt_for_travel_time()

        if not self.travel_temp:
            self.prompt_for_travel_temp()

        # make recommendations
        month_options = self.travel_df.loc[self.travel_df.loc[:, "Month"] == 'january', :]
        temp_index = (month_options['Low Temp'] <= self.travel_temp) &\
                     (month_options['High Temp'] >= self.travel_temp)
        final_options = month_options.loc[temp_index, "Town"]
        if len(final_options) == 0:
            final_options = month_options.loc[:, "Town"]
        travel_place = random.choice(final_options)
        recommendation = random.choice(travel_recs).format(place=travel_place.strip(),
                                                           month=self.travel_month.title())
        self.irc.send_dm(self.channel, self.target, recommendation)

    def prompt_for_travel_time(self):
        self.irc.send_dm(self.channel, self.target, random.choice(travel_time_questions))
        self.wait_for_text(self.random_travel_time, self.get_travel_time_user_text)

    def prompt_for_travel_temp(self):
        self.irc.send_dm(self.channel, self.target, random.choice(travel_temp_questions))
        self.wait_for_text(self.random_travel_temp, self.get_travel_temp_user_text)

    def get_travel_time_user_text(self):
        self.get_travel_time(self.user_text, take_guess=True)

    def get_travel_temp_user_text(self):
        self.get_travel_temp(self.user_text, take_guess=True)

    def get_travel_time(self, _text, take_guess=False):
        for month in trav.months.keys():
            if month in _text:
                self.travel_month = month
        for season in trav.seasons.keys():
            if season in _text:
                self.travel_month = random.choice(trav.seasons[season])

        if not self.travel_month and take_guess:
            self.random_travel_time()

    def get_travel_temp(self, _text, take_guess=False):
        words = nltk.word_tokenize(_text)
        for word in words:
            if word in temp_words.keys():
                self.travel_temp = temp_words[word]
            if word.isdigit():
                self.travel_temp = int(word)

        if not self.travel_temp and take_guess:
            self.random_travel_temp()

    def random_travel_time(self):
        self.irc.send_dm(self.channel, self.target, random.choice(travel_guess))
        self.travel_month = random.choice(trav.months.keys())

    def random_travel_temp(self):
        self.irc.send_dm(self.channel, self.target, random.choice(travel_guess))
        self.travel_temp = random.choice(list(temp_words.values()))


    def run_bot(self):
        while True:
            print(f"state: {self.bot_state}")
            if self.bot_state.is_start:
                self.start_state()
            elif self.bot_state.is_initial_outreach:
                self.initial_outreach_state()
            elif self.bot_state.is_secondary_outreach:
                self.secondary_outreach_state()
            elif self.bot_state.is_outreach_reply:
                self.outreach_reply_state()
            elif self.bot_state.is_inquiry:
                self.inquiry_state()
            elif self.bot_state.is_inquiry_super:
                self.inquiry_state()
            elif self.bot_state.is_inquiry_reply:
                self.inquiry_reply_state()
            elif self.bot_state.is_giveup_frustrated:
                self.giveup_state()
            elif self.bot_state.is_end:
                self.end_state()
            else:
                print("State error")

    def start_state(self):
        self.bot_state.reach_out()

    def initial_outreach_state(self):
        # we are always speaker one
        self.target = ""
        #                                     we are speaker one,          we are speaker two
        self.spoke_first = self.wait_for_text(self.bot_state.no_reply_one, self.bot_state.response)
        if self.spoke_first:
            # append name list
            self.get_names()
            self.target = random.choice(list(self.users))
            print(f"reaching out to {self.target}")
            self.irc.send_dm(self.channel, self.target, random.choice(initial_outreaches))
            return
        # code here (check for unique question and then branch to new state machine)
        if self.check_unique_question_hari(self.user_text):
            # fill in with logic to try unique functionality
            self.bot_state.restart()
        elif self.check_unique_question_clay(self.user_text):
            # fill in with logic to try unique functionality
            self.recommend_travel(self.user_text)
            self.bot_state.restart()
        elif self.check_unique_question_archit(self.user_text):
            # fill in with logic to try unique functionality
            self.bot_state.restart()

    def secondary_outreach_state(self):
        if self.wait_for_text(self.bot_state.retry_secondary, self.bot_state.second_response):
            self.irc.send_dm(self.channel, self.target, random.choice(secondary_outreaches))
            self.wait_for_text(self.bot_state.no_reply_after_second, self.bot_state.second_response)

    def outreach_reply_state(self):
        if self.spoke_first:  # we are speaker one
            max_retries = 3
            normalized_text = self.normalize_response(self.user_text)
            if normalized_text in pairs_outreach.keys():
                resp = get_next_outreach(normalized_text)  # should look like a question
                self.bot_state.inquiry_given()
                self.retries = 0
                self.irc.send_dm(self.channel, self.target, resp)
            elif self.retries <= max_retries:
                resp = random.choice(confused_phrases)
                self.irc.send_dm(self.channel, self.target, resp)
                self.wait_for_text(self.bot_state.retry_outreach, self.bot_state.retry_outreach)
                if self.awaiting_response:
                    return
                self.retries += 1
            else:
                self.bot_state.no_inquiry()
        else:  # we are speaker two
            normalized_text = self.normalize_response(self.user_text)
            if normalized_text in pairs_response.keys():  # intro or intro and question if they asked a question
                resp = get_next_response(normalized_text)
                self.bot_state.inquiry_given()
                self.bot_response = resp if isinstance(resp, tuple) \
                    else self.irc.send_dm(self.channel, self.target, resp)
                return
            # TODO check for unique questions (phase 3)
            resp = random.choice(confused_phrases)
            self.irc.send_dm(self.channel, self.target, resp)
            self.wait_for_text(self.bot_state.retry_outreach, self.bot_state.retry_outreach)

    def inquiry_state(self):
        if self.spoke_first:
            # bot just asked a question
            self.wait_for_text(self.bot_state.ignore_after_inquiry, self.bot_state.inquiry_response)
            if self.awaiting_response:
                return
            self.wait_for_text(self.bot_state.ignore_after_inquiry_two, self.bot_state.to_next_inquiry)
            normalized_text = self.normalize_response(self.user_text)
            if normalized_text in pairs_response.keys():
                resp = get_next_response(normalized_text)
                self.send_question_answer_pair(resp, False)  # send just answer here
            else:
                resp = random.choice(confused_phrases)
                self.irc.send_dm(self.channel, self.target, resp)
        elif self.bot_response:
            self.send_question_answer_pair(self.bot_response)
            self.bot_response = ""
        else:
            self.wait_for_text(self.bot_state.ignore_after_inquiry, self.bot_state.inquiry_response)
            if self.awaiting_response:
                return
            normalized_text = self.normalize_response(self.user_text)
            if normalized_text in pairs_response.keys():
                # question if they asked a question
                resp = get_next_response(normalized_text)
                self.bot_state.to_next_inquiry()
                self.send_question_answer_pair(resp)
            else:
                self.bot_state.ignore_after_inquiry_two()

    def inquiry_reply_state(self):
        if self.spoke_first:
            self.bot_state.happy_end()
        else:
            self.wait_for_text(self.bot_state.happy_end, self.bot_state.happy_end)

    def giveup_state(self):
        self.irc.send_dm(self.channel, self.target, random.choice(frustrated_phrases))
        self.bot_state.giveup_end()

    def end_state(self):
        self.bot_state.restart()


if __name__ == "__main__":
    main()

